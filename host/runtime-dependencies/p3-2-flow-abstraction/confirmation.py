"""Frozen isolated P3.2 confirmation. It never starts Android or invokes model transport."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from audit_io import inspect_original, save_report
from p32deps import P31, PREDECESSOR_HASH, canonical, verify_predecessor

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
RUNNER = ROOT / 'p1p2-seed-acceptance/suite_runner.py'
SPEC = Path('C:/Users/zz/AppData/Local/Temp/P3_2_抽取参数与可复用业务流程.md')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(canonical(value))


def command(cmd, output):
    try:
        run = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, encoding='utf-8', timeout=90)
        result = {'command': cmd, 'exit_code': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr}
    except subprocess.TimeoutExpired:
        result = {'command': cmd, 'exit_code': None, 'status': 'PROCESS_TIMEOUT'}
    save(output, result)
    return result


def run_suite(directory, destination, label):
    output = destination / (label + '.json')
    cmd = [sys.executable, '-X', 'utf8', str(RUNNER), str(directory), str(output)]
    run = command(cmd, destination / (label + '-command.json'))
    if run['exit_code'] != 0 or not output.exists():
        return {'group': label, 'status': 'FAIL', 'exit_code': run['exit_code']}
    ledger = json.loads(output.read_text(encoding='utf-8'))
    return {'group': label, 'status': ledger['status'], 'methods': ledger['count'], 'correct': ledger['correct'],
            'subcases': len(ledger['subcases']), 'subcases_correct': sum(s['result'] == 'PASS' for s in ledger['subcases']),
            'scope': 'CONTRACT_PROTOCOL_NOT_DEVICE_OR_REAL_MODEL', 'evidence': str(output)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--batch', required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,80}', args.batch):
        raise ValueError('INVALID_BATCH_NAME')
    destination = BASE / 'evidence' / args.batch
    destination.mkdir(parents=True, exist_ok=False)
    materials = json.loads((P31 / 'evidence/frozen-confirmation-r1/material-results.json').read_text(encoding='utf-8'))
    originals = [r for r in materials if r['repetition'] == 1]
    assert len(originals) == 4
    paths = list(BASE.glob('*.py')) + [BASE / 'tasks/plan.md', BASE / 'README.md', SPEC, RUNNER,
             P31 / 'evidence/frozen-confirmation-r1/material-results.json']
    prior = json.loads((P31 / 'evidence/frozen-confirmation-r1/freeze.json').read_text(encoding='utf-8'))
    paths += [Path(r['path']) for r in prior['materials']]
    for row in originals:
        paths += [Path(row['audit_directory']) / name for name in ('input.json', 'result.json')]
    rows = [{'path': str(p), 'sha256': sha(p)} for p in sorted(set(paths))]
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=BASE, capture_output=True, text=True, check=True).stdout.strip()
    freeze = {'source_hash': hashlib.sha256(canonical(rows).encode()).hexdigest(), 'files': rows,
              'git_head': head, 'predecessor_source_hash': PREDECESSOR_HASH,
              'time_utc': datetime.now(timezone.utc).isoformat(), 'confirmation_rounds': 3,
              'expected_p32_methods_per_round': 45, 'real_model_calls_allowed': 0, 'android_actions_allowed': 0,
              'scope': 'P3_2_OFFLINE_AND_HISTORICAL_SAVED_MATERIAL_NO_EXECUTION',
              'score': 'PROTOCOL_PASS_SEPARATE_FROM_REAL_CANDIDATE_NOT_TESTED'}
    save(destination / 'freeze.json', freeze)
    rounds = []
    for n in range(1, 4):
        rounds.append(run_suite(BASE, destination, f'p32-round-{n}'))
        print(canonical(rounds[-1]), flush=True)
    regressions = []
    for label, path in (('p31', P31), ('p12', ROOT / 'p1-2-flow-contracts'),
                        ('p24', ROOT / 'p1p2-seed-acceptance/candidate/p2-4-learning-bundle')):
        regressions.append(run_suite(path, destination, 'regression-' + label))
        print(canonical(regressions[-1]), flush=True)
    actual = []
    for row in originals:
        result = inspect_original(row['audit_directory'], [row['historical_source']])
        directory = save_report(destination / 'material-audits', result)
        fresh = command([sys.executable, '-X', 'utf8', str(BASE / 'cli.py'), '--p31-audit', row['audit_directory'],
                         '--bundle', row['historical_source'], '--output-root', str(destination / 'fresh-readback')],
                        destination / (row['case'] + '-readback-command.json'))
        status = json.loads(fresh.get('stdout', '{}')).get('status') if fresh['exit_code'] == 0 else None
        actual.append({'case': row['case'], 'analysis_status': result['status'], 'fresh_readback_status': status,
                       'original_model_status': result.get('original_model_status'),
                       'channel': 'HISTORICAL_ANDROID_SAVED_MATERIAL_READ_ONLY', 'pages': row['pages'],
                       'traces': len(result.get('trace_classification', [])), 'sources': row['sources'],
                       'candidate_present': result['candidate_flow'] is not None,
                       'source_unchanged': result.get('source_unchanged', False), 'output_directory': str(directory),
                       'new_model_calls': 0, 'new_device_actions': 0})
    unchanged = all(sha(r['path']) == r['sha256'] for r in rows) and verify_predecessor() == PREDECESSOR_HASH
    protocol_pass = all(r['status'] == 'PASS' and r['methods'] == 45 and r['subcases'] == r['subcases_correct'] for r in rounds)
    regression_pass = all(r['status'] == 'PASS' and r['subcases'] == r['subcases_correct'] for r in regressions)
    read_only_pass = all(r['analysis_status'] == r['fresh_readback_status'] == 'BLOCKED_NO_CANDIDATE'
                        and r['source_unchanged'] and not r['candidate_present'] for r in actual)
    summary = {'overall': 'PARTIAL' if protocol_pass and regression_pass and read_only_pass and unchanged else 'FAIL',
               'protocol': 'PASS' if protocol_pass else 'FAIL', 'regressions': 'PASS' if regression_pass else 'FAIL',
               'real_candidate_parameterization': 'BLOCKED_NO_CANDIDATE', 'business_execution': 'NOT_TESTED',
               'actual_model_calls': 0, 'actual_device_actions': 0, 'sources_unchanged': unchanged,
               'rounds': rounds, 'regressions_detail': regressions, 'real_material_audits': actual,
               'old_p1p2_status': 'PARTIAL_RETAINED', 'old_p31_status': 'PARTIAL_RETAINED',
               'scope': 'STOP_AT_P3_2_NO_P3_3'}
    save(destination / 'summary.json', summary)
    print(canonical({'overall': summary['overall'], 'summary': str(destination / 'summary.json')}), flush=True)
    return 0 if summary['overall'] == 'PARTIAL' else 1


if __name__ == '__main__': raise SystemExit(main())
