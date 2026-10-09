"""Frozen offline confirmation; no model clients, Android execution or P3.4 publication."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from p33deps import P32, P14, PREDECESSOR_HASH, canonical, verify_predecessor
from material_io import inspect_material, save_report
from logic_examples import collect_examples

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
P31 = ROOT / 'p3-1-draft-generator'
RUNNER = ROOT / 'p1p2-seed-acceptance/suite_runner.py'
SPEC = Path('C:/Users/zz/AppData/Local/Temp/P3_3_分层检查与授权实测.md')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(canonical(value))


def command(cmd, output):
    try:
        run = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, encoding='utf-8', timeout=60)
        result = {'command': cmd, 'exit_code': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr}
    except subprocess.TimeoutExpired:
        result = {'command': cmd, 'exit_code': None, 'status': 'PROCESS_TIMEOUT'}
    save(output, result)
    return result


def run_suite(directory, destination, label):
    output = destination / (label + '.json')
    run = command([sys.executable, '-X', 'utf8', str(RUNNER), str(directory), str(output)],
                  destination / (label + '-command.json'))
    if run['exit_code'] != 0 or not output.exists():
        return {'group': label, 'status': 'FAIL', 'exit_code': run['exit_code']}
    ledger = json.loads(output.read_text(encoding='utf-8'))
    return {'group': label, 'status': ledger['status'], 'methods': ledger['count'], 'correct': ledger['correct'],
            'subcases': len(ledger['subcases']), 'subcases_correct': sum(s['result'] == 'PASS' for s in ledger['subcases']),
            'channel': 'OFFLINE_CONTRACT_AND_LOGIC_NOT_DEVICE', 'evidence': str(output)}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--batch', required=True); args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,80}', args.batch): raise ValueError('INVALID_BATCH_NAME')
    destination = BASE / 'evidence' / args.batch
    destination.mkdir(parents=True, exist_ok=False)
    material_path = P31 / 'evidence/frozen-confirmation-r1/material-results.json'
    originals = [r for r in json.loads(material_path.read_text(encoding='utf-8')) if r['repetition'] == 1]
    if len(originals) != 4: raise ValueError('MATERIAL_CATALOG_CHANGED')
    prior = json.loads((P32 / 'evidence/frozen-confirmation-r1/freeze.json').read_text(encoding='utf-8'))
    paths = list(BASE.glob('*.py')) + [BASE / 'README.md', BASE / 'tasks/plan.md', SPEC, RUNNER, material_path,
             P14 / 'dependency-pins.json'] + list(P14.glob('*.py')) + list((ROOT / 'p1-3-flow-compiler').glob('*.py'))
    paths += [Path(r['path']) for r in prior['files']]
    rows = [{'path': str(p), 'sha256': sha(p)} for p in sorted(set(paths))]
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=BASE, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=BASE, capture_output=True, text=True, check=True).stdout
    freeze = {'source_hash': hashlib.sha256(canonical(rows).encode()).hexdigest(), 'files': rows,
              'git_head': head, 'uncommitted_status': dirty, 'predecessor_hash': PREDECESSOR_HASH,
              'time_utc': datetime.now(timezone.utc).isoformat(), 'rounds': 3, 'expected_methods_per_round': 40,
              'real_model_calls_allowed': 0, 'android_actions_allowed': 0,
              'scoring': 'CONTRACT_PASS_SEPARATE_FROM_BLOCKED_REAL_EXECUTION', 'scope': 'P3_3_ONLY'}
    save(destination / 'freeze.json', freeze)
    rounds = []
    for n in range(1, 4):
        rounds.append(run_suite(BASE, destination, f'p33-round-{n}')); print(canonical(rounds[-1]), flush=True)
    regressions = []
    for label, path in (('p32', P32), ('p13', ROOT / 'p1-3-flow-compiler'), ('p14', P14)):
        regressions.append(run_suite(path, destination, 'regression-' + label)); print(canonical(regressions[-1]), flush=True)
    actual = []
    for row in originals:
        report = inspect_material(row['audit_directory'], [row['historical_source']])
        directory = save_report(destination / 'material-audits', report)
        run = command([sys.executable, '-X', 'utf8', str(BASE / 'cli.py'), '--read-saved', str(directory)],
                      destination / (row['case'] + '-readback-command.json'))
        readback = json.loads(run.get('stdout', '{}')) if run['exit_code'] == 0 else {}
        actual.append({'case': row['case'], 'status': report['status'], 'source_unchanged': report['source_unchanged'],
                       'readback': readback.get('readback'), 'readback_status': readback.get('status'),
                       'model_calls': report['model_calls'], 'device_actions': report['device_actions'],
                       'layers': report['layers'], 'evidence': str(directory), 'channel': report['evidence_channel']})
    examples = collect_examples(); save(destination / 'logic-examples.json', examples)
    unchanged = all(sha(r['path']) == r['sha256'] for r in rows) and verify_predecessor() == PREDECESSOR_HASH
    logic_pass = all(r['status'] == 'PASS' and r['methods'] == 40 and r['subcases'] == r['subcases_correct'] for r in rounds)
    regression_pass = all(r['status'] == 'PASS' and r['subcases'] == r['subcases_correct'] for r in regressions)
    material_pass = all(r['status'] == r['readback_status'] == 'BLOCKED_NO_CANDIDATE'
                        and r['readback'] == 'PASS' and r['source_unchanged'] for r in actual)
    examples_pass = all(r['public_receipt']['status'] == 'SIMULATION_VERIFIED'
                        and r['independent_logic_score']['status'] == 'LOGIC_ORACLE_CONFIRMED'
                        and r['independent_logic_score']['wrong_action'] is False
                        and r['independent_logic_score']['false_success'] is False for r in examples)
    summary = {'overall': 'PARTIAL' if all((logic_pass, regression_pass, material_pass, examples_pass, unchanged)) else 'FAIL',
               'isolated_implementation': 'PASS' if logic_pass and examples_pass else 'FAIL',
               'regressions': 'PASS' if regression_pass else 'FAIL', 'sources_unchanged': unchanged,
               'real_candidate': 'BLOCKED_NO_CANDIDATE', 'authorized_android_execution': 'BLOCKED_NATIVE_TRANSPORT',
               'real_candidate_execution_and_reuse_checkpoint': 'NOT_PASSED', 'actual_model_calls': 0,
               'actual_android_actions': 0, 'rounds': rounds, 'regression_details': regressions,
               'material_audits': actual, 'logic_examples': len(examples), 'logic_examples_only': True,
               'old_failures_and_partial_retained': True, 'ready_for_p3_4': False,
               'scope': 'STOP_AT_P3_3_NO_MODEL_OR_ANDROID_EXECUTION'}
    save(destination / 'summary.json', summary)
    print(canonical({'overall': summary['overall'], 'summary': str(destination / 'summary.json')}), flush=True)
    return 0 if summary['overall'] == 'PARTIAL' else 1


if __name__ == '__main__': raise SystemExit(main())
