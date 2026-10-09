"""Frozen confirmation: offline lifecycle and historical readback, never Android/GPT."""
import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from p34deps import ROOT, P33, PREDECESSOR, p33, trusted, canonical, digest, compiler, adapter, records, verify_predecessor
from knowledge import KnowledgeLibrary
from material_package import archive_material, read_archive
from test_publication import supplement

BASE = Path(__file__).resolve().parent
P31 = ROOT / 'p3-1-draft-generator'
RUNNER = ROOT / 'p1p2-seed-acceptance/suite_runner.py'
SPEC = Path('C:/Users/zz/AppData/Local/Temp/P3_4_版本化发布与知识包整理.md')
support = trusted('test_support', p33.P14)
evaluator = trusted('evaluator', P33)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    with Path(path).open('x', encoding='utf-8', newline='\n') as stream: stream.write(canonical(value))


def command(cmd, output):
    try:
        run = subprocess.run(cmd, cwd=BASE, capture_output=True, text=True, encoding='utf-8', timeout=60)
        result = {'command': cmd, 'exit_code': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr}
    except subprocess.TimeoutExpired: result = {'command': cmd, 'exit_code': None, 'status': 'PROCESS_TIMEOUT'}
    save(output, result)
    return result


def suite(path, destination, label):
    output = destination / (label + '.json')
    run = command([sys.executable, '-X', 'utf8', str(RUNNER), str(path), str(output)], destination / (label + '-command.json'))
    if run['exit_code'] != 0 or not output.exists(): return {'group': label, 'status': 'FAIL'}
    out = json.loads(output.read_text(encoding='utf-8'))
    return {'group': label, 'status': out['status'], 'methods': out['count'], 'correct': out['correct'],
            'subcases': len(out['subcases']), 'subcases_correct': sum(r['result'] == 'PASS' for r in out['subcases']),
            'evidence': str(output), 'channel': 'OFFLINE_CONTRACT_OR_LOGIC_NOT_DEVICE'}


def logic_examples(destination):
    rows = []
    for skill, demo, unseen in (('SetBrightness', 60, 80), ('SetTemperature', 22, 30), ('SetPower', 'on', 'off')):
        flow, package, task = p33.p14.fixture_bundle(skill, demo)
        library_root = destination / ('simulation-store-' + skill)
        library = KnowledgeLibrary.create(library_root, approved_roots=[BASE])
        try:
            metadata = supplement(); metadata['human_cost'] = {'actions': None, 'minutes': None}
            draft = library.save_draft(canonical(flow), package, metadata, 0, source_paths=[BASE / 'tasks/plan.md'])
            key = draft['key']; library.flows.check(key, 1, task, None)
            plans = []
            property_name = compiler.old.CAPS[skill]['property']
            state_key = task['inputs']['entity']['entity_id'] + '.' + property_name
            for category, value in (('DEMONSTRATION', demo), ('UNSEEN_PARAMETER', unseen), ('ALREADY_SATISFIED', demo)):
                current_task = copy.deepcopy(task); current_task['inputs']['value'] = value
                initial = dict(support.STATE)
                initial[state_key] = value if category == 'ALREADY_SATISFIED' else (
                    'off' if value == 'on' else 'on') if skill == 'SetPower' else 0 if skill == 'SetBrightness' else 16
                clock = support.Clock(); port = support.RoomPort(clock, initial); events = []
                def callback(port, call):
                    cap = compiler.old.CAPS[call['skill']]; port.apply(call)
                    events.append({'step_id': 'set_value', 'target_key': state_key, 'value': call['args'][cap['argument']],
                                   'submitted': True, 'effective': True})
                    return {'final_status': 'SUCCESS', 'verification_result': True}
                port.on_call = callback
                plan = compiler.compile_flow(flow, package, current_task, None); plans.append(plan)
                result = adapter.FlowAdapter(True, clock=clock).validate_candidate(library.flows, key, current_task,
                    records.ValidationAuthority(key, 'test.fixture.operator', True), lambda: support.policy_for(plan), port)
                if result.evidence is not None:
                    library.record_validation(key, library.flows.load(key)['revision'], result.evidence)
                rows.append({'skill': skill, 'category': category, 'channel': 'HANDWRITTEN_LOGIC_SIMULATION_NOT_LEARNED_OR_ANDROID',
                    'inputs': current_task['inputs'], 'initial_state': initial, 'final_state': port.state,
                    'write_events': events, 'public_receipt': result.receipt,
                    'score': evaluator.score_execution(plan, result.receipt, initial, port.state, events)})
            authority = records.PublishAuthority(key, 'test.fixture.operator', plans[-1].to_dict()['environment_hash'], 'LOGIC_SIMULATION', True)
            published = library.publish_logic(key, library.flows.load(key)['revision'], authority)
            save(destination / (skill + '-inert-export.json'), library.export(key))
            expected = digest(published)
        finally: library.close()
        run = command([sys.executable, '-X', 'utf8', str(BASE / 'cli.py'), '--read-key', key,
                       '--library-root', str(library_root), '--source-root', str(BASE)], destination / (skill + '-readback-command.json'))
        readback = json.loads(run.get('stdout', '{}')) if run['exit_code'] == 0 else {}
        rows.append({'skill': skill, 'category': 'PUBLISHED_LOGIC_NEW_PROCESS_READBACK',
                     'channel': 'HANDWRITTEN_LOGIC_SIMULATION_NOT_LEARNED_OR_ANDROID',
                     'digest_match': digest(readback) == expected, 'logic_retrievable': readback.get('logic_retrievable'),
                     'formal_retrievable': readback.get('formal_retrievable'), 'execution_authority': readback.get('execution_authority'),
                     'points': len(readback.get('actual_points', [])), 'setting_points': sum(p['setting_trial'] for p in readback.get('actual_points', []))})
    return rows


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--batch', required=True); args = parser.parse_args()
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,80}', args.batch): raise ValueError('INVALID_BATCH_NAME')
    destination = BASE / 'evidence' / args.batch; destination.mkdir(parents=True, exist_ok=False)
    catalog_path = P31 / 'evidence/frozen-confirmation-r1/material-results.json'
    originals = [r for r in json.loads(catalog_path.read_text(encoding='utf-8')) if r['repetition'] == 1]
    if len(originals) != 4: raise ValueError('MATERIAL_CATALOG_CHANGED')
    paths = list(BASE.glob('*.py')) + [BASE / 'README.md', BASE / 'tasks/plan.md', SPEC, RUNNER, catalog_path]
    paths += [Path(r['path']) for r in PREDECESSOR['files']]
    paths += [Path(r['historical_source']) for r in originals]
    paths += [Path(r['audit_directory']) / name for r in originals for name in ('input.json', 'result.json')]
    files = [{'path': str(p), 'sha256': sha(p)} for p in sorted(set(paths))]
    head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=BASE, capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(['git', 'status', '--porcelain'], cwd=BASE, capture_output=True, text=True, check=True).stdout
    freeze = {'source_hash': digest(files), 'files': files, 'git_head': head, 'uncommitted_status': dirty,
        'predecessor_hash': PREDECESSOR['source_hash'], 'time_utc': datetime.now(timezone.utc).isoformat(),
        'rounds': 3, 'expected_methods': 48, 'real_model_calls_allowed': 0, 'android_actions_allowed': 0,
        'scope': 'P3_4_ISOLATED_NO_P4', 'scoring': 'OFFLINE_PASS_DOES_NOT_SATISFY_REAL_FLOW_CHECKPOINT'}
    save(destination / 'freeze.json', freeze)
    rounds = [suite(BASE, destination, 'p34-round-' + str(n)) for n in range(1, 4)]
    for r in rounds: print(canonical(r), flush=True)
    regressions = [suite(path, destination, 'regression-' + name) for name, path in
                   (('p33', P33), ('p32', p33.P32), ('p14', p33.P14))]
    for r in regressions: print(canonical(r), flush=True)
    materials = []
    for row in originals:
        directory = archive_material(row['audit_directory'], [row['historical_source']], destination / 'material-archives', approved_roots=[ROOT])
        value = read_archive(directory, approved_roots=[ROOT])
        run = command([sys.executable, '-X', 'utf8', str(BASE / 'cli.py'), '--read-archive', str(directory),
                       '--source-root', str(ROOT)], destination / (row['case'] + '-readback-command.json'))
        readback = json.loads(run.get('stdout', '{}')) if run['exit_code'] == 0 else {}
        materials.append({'case': row['case'], 'status': value['status'], 'readback': readback.get('readback'),
            'digest_match': readback.get('archive_digest') == digest(value), 'archive': str(directory),
            'source_refs': value['source_refs'], 'pages': sum(len(b['pages']) for b in value['learning_bundles']),
            'navigation': sum(len(b['navigation']) for b in value['learning_bundles']),
            'model_original_present': value['model_original'] is not None, 'human_cost': value['human_cost'],
            'execution_authority': False, 'formal_retrievable': False, 'new_model_calls': 0, 'new_android_actions': 0})
    save(destination / 'material-results.json', materials)
    examples = logic_examples(destination); save(destination / 'logic-examples.json', examples)
    unchanged = all(sha(r['path']) == r['sha256'] for r in files) and verify_predecessor()['source_hash'] == PREDECESSOR['source_hash']
    local_ok = all(r['status'] == 'PASS' and r.get('methods') == 48 and r['subcases'] == r['subcases_correct'] for r in rounds)
    regression_ok = all(r['status'] == 'PASS' and r['subcases'] == r['subcases_correct'] for r in regressions)
    material_ok = all(r['status'] == 'BLOCKED_NO_CANDIDATE' and r['readback'] == 'PASS' and r['digest_match'] for r in materials)
    runtime_rows = [r for r in examples if 'public_receipt' in r]
    reload_rows = [r for r in examples if 'digest_match' in r]
    example_ok = all(r['public_receipt']['status'] == 'SIMULATION_VERIFIED' and r['score']['status'] == 'LOGIC_ORACLE_CONFIRMED'
                     and not r['score']['wrong_action'] and not r['score']['false_success'] for r in runtime_rows)
    example_ok = example_ok and all(r['digest_match'] and r['logic_retrievable'] and not r['formal_retrievable']
                                  and not r['execution_authority'] and r['points'] == 3 and r['setting_points'] == 2 for r in reload_rows)
    summary = {'overall': 'PARTIAL' if all((local_ok, regression_ok, material_ok, example_ok, unchanged)) else 'FAIL',
        'isolated_implementation': 'PASS' if local_ok and example_ok else 'FAIL',
        'regressions': 'PASS' if regression_ok else 'FAIL', 'material_archiving_and_reload': 'PASS' if material_ok else 'FAIL',
        'real_candidate': 'BLOCKED_NO_CANDIDATE', 'real_flow_publication': 'BLOCKED_REAL_FLOW_VERIFICATION_REQUIRED',
        'native_flow_transport': 'BLOCKED_NOT_CONNECTED', 'p3_cumulative_checkpoint': 'NOT_PASSED',
        'ready_for_p4': False, 'old_failures_and_partial_retained': True, 'actual_model_calls': 0, 'actual_android_actions': 0,
        'rounds': rounds, 'regression_details': regressions, 'materials': len(materials), 'logic_runtime_examples': len(runtime_rows),
        'logic_reload_examples': len(reload_rows), 'formal_published_flows': 0, 'sources_unchanged': unchanged,
        'scope': 'STOP_AT_P3_4_NO_PRODUCT_OR_P4_ENTRY', 'frozen_source_hash': freeze['source_hash']}
    save(destination / 'summary.json', summary)
    print(canonical({'overall': summary['overall'], 'summary': str(destination / 'summary.json')}), flush=True)
    return 0 if summary['overall'] == 'PARTIAL' else 1


if __name__ == '__main__': raise SystemExit(main())
