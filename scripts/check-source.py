"""Parse public sources and check common credentials without importing modules.

This is a release hygiene check, not an exhaustive secret detector or E2E test.
Use --staged after git add to scan the actual index instead of working files.
No matched secret values are printed.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED = {'.git', 'build', '.gradle', '.idea', '__pycache__', '.pytest_cache',
            '.venv', 'venv', 'private', 'backups', 'snapshots', 'output', 'evidence'}
FORBIDDEN_SUFFIXES = {'.keystore', '.jks', '.pem', '.key', '.p12', '.pfx',
                      '.token', '.apk', '.aab', '.class', '.dex', '.db'}
SECRET_PATTERNS = {
    'openai-like-token': re.compile(r'\bsk-(?:proj-|svcacct-)?(?!fake|test|dummy|example)[A-Za-z0-9_-]{28,}'),
    'github-token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'private-key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'aws-access-key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
}


def git(*args: str) -> bytes:
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def entries(staged: bool):
    if staged:
        names = git('ls-files', '-z').split(b'\0')
        for name in names:
            if name:
                rel = name.decode('utf-8')
                yield Path(rel), git('show', ':' + rel)
    else:
        for path in sorted(ROOT.rglob('*')):
            rel = path.relative_to(ROOT)
            if not path.is_file() or set(rel.parts) & EXCLUDED:
                continue
            if path.suffix.lower() in FORBIDDEN_SUFFIXES:
                # Build artifacts are excluded above; credentials in the source
                # tree must not be silently ignored by this working-tree check.
                yield rel, path.read_bytes()
            elif path.suffix.lower() not in {'.pyc', '.pyo', '.log'}:
                yield rel, path.read_bytes()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--staged', action='store_true')
    args = parser.parse_args()
    failures = []
    counts = {'files': 0, 'python': 0, 'xml_svg': 0, 'json': 0, 'markdown_links': 0}
    for rel, raw in entries(args.staged):
        counts['files'] += 1
        if rel.suffix.lower() in FORBIDDEN_SUFFIXES or rel.name == '.env' or rel.name.startswith('.env.') and rel.name != '.env.example':
            failures.append({'path': rel.as_posix(), 'error': 'PRIVATE_OR_GENERATED_FILE'})
            continue
        try:
            content = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            failures.append({'path': rel.as_posix(), 'error': 'UNEXPECTED_BINARY'})
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                failures.append({'path': rel.as_posix(), 'error': 'POSSIBLE_SECRET', 'kind': label})
        try:
            if rel.suffix == '.py':
                ast.parse(content, filename=rel.as_posix())
                counts['python'] += 1
            elif rel.suffix in {'.xml', '.svg'}:
                ET.fromstring(content)
                counts['xml_svg'] += 1
            elif rel.suffix == '.json':
                json.loads(content)
                counts['json'] += 1
            elif rel.suffix == '.md':
                for target in re.findall(r'\]\(([^\s)]+)\)', content):
                    if '://' in target or target.startswith('#'):
                        continue
                    path = (ROOT / rel.parent / target.split('#')[0]).resolve()
                    if not path.is_relative_to(ROOT) or not path.exists():
                        failures.append({'path': rel.as_posix(), 'error': 'BROKEN_LOCAL_LINK', 'target': target})
                    counts['markdown_links'] += 1
        except (SyntaxError, ET.ParseError, ValueError) as error:
            failures.append({'path': rel.as_posix(), 'error': type(error).__name__})
    print(json.dumps({'scope': 'git-index' if args.staged else 'working-tree',
                      'counts': counts, 'failure_count': len(failures),
                      'failures': failures, 'models_called': 0, 'device_operations': 0},
                     ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
