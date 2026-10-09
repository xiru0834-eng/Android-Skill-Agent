"""Frozen offline confirmation. Real saved Android material != new Android/model execution."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
from unittest.mock import patch

from draft_generator import Budget, DraftGenerator
from learning_request import request_from_store, model_messages
from p31deps import canonical, digest, verify_dependencies

BASE = Path(__file__).resolve().parent
SEED = Path('D:/Codex-deliveries/smarthome-ui-polish/p1p2-seed-acceptance')
P24 = SEED / 'candidate/p2-4-learning-bundle'
PHONE = P24 / 'evidence/seed-confirmation-v4-r3/phone-readonly'
PAD = P24 / 'evidence/seed-confirmation-v4-r3/emulator-5556-r3'
PAD_ROOM = SEED / 'evidence/confirmation-v4/round-3/pad-parameterroom-readonly'
CASES = [
    ('phone-parameter-room', PHONE / 'PARAMETERROOM-bundle.json', PHONE / 'phone-memory.sqlite'),
    ('phone-existing-draft', PHONE / 'EXISTING_DRAFT-bundle.json', PHONE / 'phone-memory.sqlite'),
    ('pad-parameter-room', PAD_ROOM / 'learning-bundle.json', PAD_ROOM / 'memory.sqlite'),
    ('pad-guided-navigation', PAD / 'learning-bundle.json', PAD / 'memory.sqlite')]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f: f.write(canonical(value))


def capture(argv, cwd, output):
    started = time.monotonic()
    run = subprocess.run(argv, cwd=cwd, capture_output=True, encoding='utf-8', errors='replace', timeout=60)
    value = {'argv': argv, 'cwd': str(cwd), 'returncode': run.returncode,
             'stdout': run.stdout, 'stderr': run.stderr, 'elapsed_ms': (time.monotonic() - started) * 1000}
    write(output, value)
    if run.returncode: raise RuntimeError('CONFIRMATION_COMMAND_FAILED')
    return value


def freeze(batch):
    products = [p for p in sorted(BASE.rglob('*')) if p.is_file() and 'evidence' not in p.parts
                and '.git' not in p.parts and '__pycache__' not in p.parts
                and (p.suffix in ('.py', '.json') or p == BASE / 'tasks/plan.md')]
    rows = [{'path': str(p), 'sha256': sha(p)} for p in products]
    sources = sorted({p for _, b, s in CASES for p in (b, s)})
    manifest = {'product_files': rows, 'source_hash': digest(rows),
                'materials': [{'path': str(p), 'sha256': sha(p)} for p in sources],
                'scope': 'OFFLINE_P3_1_PROTOCOL_AND_REAL_SAVED_MATERIAL_PROJECTION',
                'paid_model_calls_allowed': 0, 'android_actions_allowed': 0,
                'confirmation_rounds': 3, 'baseline': str(SEED / 'REPORT.md')}
    write(batch / 'freeze.json', manifest)
    return manifest


def main():
    batch = BASE / 'evidence/frozen-confirmation-r1'
    batch.mkdir(parents=True, exist_ok=False)
    manifest = freeze(batch)
    verify_dependencies()
    capture([sys.executable, '-X', 'utf8', str(SEED / 'acceptance_freeze.py'), 'verify'], SEED, batch / 'predecessor-before.json')
    runner = SEED / 'suite_runner.py'
    for number in range(1, 4):
        capture([sys.executable, '-X', 'utf8', str(runner), str(BASE), str(batch / f'protocol-r{number}.json')], BASE,
                batch / f'protocol-command-r{number}.json')
    material_rows = []
    for name, bundle_path, store_path in CASES:
        original = json.loads(bundle_path.read_text(encoding='utf-8'))
        for number in range(1, 4):
            before = sha(store_path)
            # Actual Store and Queries with device/network APIs actively blocked in this process.
            with (patch('socket.socket', side_effect=AssertionError('NETWORK_FORBIDDEN')),
                  patch('subprocess.Popen', side_effect=AssertionError('DEVICE_PROCESS_FORBIDDEN'))):
                request = request_from_store(store_path, original['environment'], [original['bundle_id']],
                                             '学习已有公开操作方法 / learn reusable control from public evidence')
                result = DraftGenerator(batch / 'material-audits', Budget()).run(request)
            directory = Path(result['audit_directory'])
            reread = capture([sys.executable, '-X', 'utf8', '-c',
                'import json,sys;from pathlib import Path;from p31deps import digest;'
                'p=Path(sys.argv[1]);v=json.loads((p/"input.json").read_text(encoding="utf-8"));'
                'core={k:x for k,x in v.items() if k not in ("input_digest","request_id")};'
                'assert v["input_digest"]==digest(core);'
                'r=json.loads((p/"result.json").read_text(encoding="utf-8"));'
                'assert r["calls"]==0 and r["status"]=="MODEL_CONFIG_MISSING";'
                'print(json.dumps({"fresh_process_readback":"PASS","status":r["status"],"sources":len(v["source_ids"])}))', str(directory)],
                BASE, batch / f'{name}-readback-r{number}.json')
            row = {'case': name, 'repetition': number, 'historical_source': str(bundle_path),
                   'source_channel': 'REAL_ANDROID_SAVED_MATERIAL', 'new_device_execution': False,
                   'audit_directory': str(directory), 'input_digest': request['input_digest'],
                   'environment': request['environment'], 'pages': len(request['material']['pages']),
                   'sources': len(request['source_ids']), 'traces': len(request['material']['traces']),
                   'knowledge_gaps': request['knowledge_gaps'], 'store_audit': request['store_audit'],
                   'store_unchanged': before == sha(store_path), 'readback': 'PASS',
                   'model_status': result['status'], 'actual_model_calls': result['calls'],
                   'execution_authority': result['execution_authority']}
            if not row['store_unchanged'] or row['actual_model_calls'] or row['execution_authority']:
                raise RuntimeError('ISOLATION_FAILED')
            material_rows.append(row)
    write(batch / 'material-results.json', material_rows)
    for module, folder in [('p1-contracts', SEED.parent / 'p1-2-flow-contracts'),
                           ('p2-bundle', P24)]:
        capture([sys.executable, '-X', 'utf8', str(runner), str(folder), str(batch / f'regression-{module}.json')],
                folder, batch / f'regression-command-{module}.json')
    capture([sys.executable, '-X', 'utf8', str(SEED / 'acceptance_freeze.py'), 'verify'], SEED, batch / 'predecessor-after.json')
    drift = [r['path'] for r in manifest['product_files'] + manifest['materials'] if sha(Path(r['path'])) != r['sha256']]
    write(batch / 'integrity-after.json', {'status': 'PASS' if not drift else 'FAIL', 'drift': drift})
    write(batch / 'summary.json', {'local_protocol': 'PASS', 'material_projection': '12/12',
          'material_independent_conditions': 4, 'repetitions': 3, 'new_device_tasks': 0, 'real_gpt': 'NOT_TESTED',
          'actual_model_calls': 0, 'publishing_or_execution': 0,
          'P3_1_ACCEPTANCE': 'PARTIAL', 'P1P2_INTEGRATION': 'PARTIAL_PRESERVED', 'source_hash': manifest['source_hash']})
    print(canonical({'status': 'PARTIAL', 'batch': str(batch), 'real_gpt': 'NOT_TESTED'}))


if __name__ == '__main__': main()
