"""Seal existing evidence only: no Android, model, state initialization or repair."""
import hashlib
import json
import math
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'evidence/final-delivery-r15'
PHONE = 'g3-phone-normal-ui-r9-default-r15'
TARGET = 'g4-emulator-normal-ui-r7-default-r15'


def read(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, data):
    # Derived indexes never replace original device/model receipts.
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def percentiles(values):
    values = sorted(v for v in values if isinstance(v, (int, float)))
    if not values:
        return {'n': 0, 'p50_ms': None, 'p95_ms': None}
    # Frozen nearest-rank descriptive statistic, not a population estimate.
    return {'n': len(values), 'p50_ms': values[math.ceil(.5 * len(values)) - 1],
            'p95_ms': values[math.ceil(.95 * len(values)) - 1]}


def cases(group):
    result = []
    for item in read('evidence/' + group + '/registered-cases.json'):
        path = 'evidence/' + group + '/' + item['name'] + '.json'
        data = read(path)
        receipt = data.get('ui', {}).get('result', {}) or {}
        selection = data.get('ui', {}).get('selection', {}) or {}
        result.append({'case': data['case'], 'source': path, 'sha256': sha(ROOT / path),
            'host': data['host'], 'expected': data['expected'], 'final_status': data['final_status'],
            'passed': data['assessment']['passed'], 'wrong_action': data['assessment']['wrong_action'],
            'false_success': data['assessment']['false_success'],
            'request_id': selection.get('request_id'), 'flow_hash': data.get('flow_hash'),
            'task_id': receipt.get('task_id'), 'process_session': receipt.get('process_session'),
            'service_entry_hit': receipt.get('service_entry_hit', False),
            'whole_flow_verified': receipt.get('verification_result', False),
            'completed_steps': receipt.get('completed_steps'),
            'actual_state': data['after']['state'], 'business_events': data['after']['events'],
            'sdk_input_count': len(receipt.get('execution_actions', [])),
            'total_evaluator_ui_ms': data.get('latency_ms'), 'runtime_ms': receipt.get('latency', {}).get('runtime_ms'),
            'launch_wait_ms': receipt.get('latency', {}).get('launch_wait_ms')})
    summary = read('evidence/' + group + '/summary.json')
    assert len(result) == summary['executed'] == summary['planned']
    assert sum(bool(c['passed']) for c in result) == summary['expected_behavior_passed']
    assert sum(bool(c['wrong_action']) for c in result) == summary['wrong_action']
    assert sum(bool(c['false_success']) for c in result) == summary['false_success']
    for case in result:
        if case['final_status'] in ('SUCCESS', 'NO_ACTION_REQUIRED'):
            assert case['whole_flow_verified'] and case['completed_steps'] == 4
    return {'summary': summary, 'cases': result,
        'latency': {'method': 'NEAREST_RANK; small-sample descriptive only',
            'total_evaluator_ui': percentiles([c['total_evaluator_ui_ms'] for c in result]),
            'positive_total_evaluator_ui': percentiles([c['total_evaluator_ui_ms'] for c in result if c['expected'] == 'SUCCESS']),
            'native_invoke_runtime': percentiles([c['runtime_ms'] for c in result]),
            'notes': 'Total includes evaluator UI driving and polling, not pure user latency; cancellation includes deliberate late-callback wait. Native runtime_ms includes launch deadline.'}}


def costs():
    ledgers = []
    states = Counter()
    for path in sorted((ROOT / 'evidence').rglob('paid-budget.json')):
        data = json.loads(path.read_text(encoding='utf-8'))
        assert data['attempts'] == len(data['rows'])
        counts = Counter(row['state'] for row in data['rows'])
        states.update(counts)
        ledgers.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path),
            'attempts': data['attempts'], 'states': dict(counts),
            'guard_exposure_usd': data['exposureNanoUsd'] / 1e9,
            'settled_guard_usd': sum(row['nanoUsd'] for row in data['rows'] if row['state'] == 'SETTLED') / 1e9,
            'input_tokens': sum(row.get('inputTokens', 0) for row in data['rows']),
            'output_tokens': sum(row.get('outputTokens', 0) for row in data['rows'])})
    generation = []
    for batch in ('g2-real-generation-r1', 'g2-real-generation-r2'):
        paths = list((ROOT / 'evidence' / batch / 'audits').glob('*/01-response.json'))
        assert len(paths) == 1
        path = paths[0]
        data = json.loads(path.read_text(encoding='utf-8'))
        generation.append({'path': path.relative_to(ROOT).as_posix(), 'sha256': sha(path),
            'request_id': data['request_id'], 'usage': data['usage'], 'finish_reason': data['finish_reason']})
    return {'g3_g4_attempts': sum(x['attempts'] for x in ledgers), 'g3_g4_states': dict(states),
        'g2_generation_returned_requests': len(generation),
        'total_request_attempts_in_this_candidate_evidence': sum(x['attempts'] for x in ledgers) + len(generation),
        'g3_g4_guard_exposure_usd_not_invoice': sum(x['guard_exposure_usd'] for x in ledgers),
        'g3_g4_settled_guard_usd_not_invoice': sum(x['settled_guard_usd'] for x in ledgers),
        'actual_billed_usd': None, 'actual_invoice_status': 'NOT_AVAILABLE',
        'notes': 'All retained repair batches included, not merely final successes. SETTLED means local budget accounting from token usage, not provider invoice. UNKNOWN_RESERVED remains exposure, never assumed free. G2 usage reported separately; historical invalid cost metadata excluded.',
        'generation': generation, 'ledgers': ledgers}


def freeze():
    rows = []
    suffixes = {'.py', '.ps1', '.java', '.xml', '.gradle', '.properties', '.md', '.json'}
    for path in sorted(ROOT.rglob('*')):
        rel = path.relative_to(ROOT)
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(p in {'.git', 'private', 'evidence', '__pycache__', 'build'} for p in rel.parts):
            continue
        rows.append({'path': rel.as_posix(), 'sha256': sha(path), 'bytes': path.stat().st_size})
    baseline = ROOT.parent / 'native-learning-candidate-v92'
    originals = []
    for name in ('PortableSkillRuntime.java', 'AccessibilityBindingResolver.java',
                 'AccessibilityRangeExecutor.java', 'PortableSkillCodec.java'):
        rel = Path('native/app/src/main/java/edu/sydney/probe') / name
        # The preserved v92 directory is the native project root itself.
        a, b = ROOT / rel, baseline / Path(*rel.parts[1:])
        originals.append({'path': rel.as_posix(), 'baseline_sha256': sha(b),
                          'candidate_sha256': sha(a), 'unchanged': sha(a) == sha(b)})
    assert all(x['unchanged'] for x in originals)
    apk = ROOT / 'native/build/manual/flow-probe-v93-r15.apk'
    deployment = read('evidence/r15-deployment-hashes.json')
    assert all(x['match'] and x['installed_sha256'] == sha(apk) for x in deployment)
    apksigner = 'D:/python_code/closed-loop-gui-agent/tools/android-sdk/build-tools/34.0.0/apksigner.bat'
    command = ['powershell', '-NoProfile', '-Command', "& '" + apksigner + "' verify --verbose --print-certs '" + str(apk) + "'"]
    signer = subprocess.run(command, cwd=ROOT, capture_output=True, check=True)
    output = signer.stdout.decode('utf-8', errors='replace')
    (OUT / 'apk-signature.txt').write_text(output, encoding='utf-8')
    tracked_diff = subprocess.run(['git', 'diff', '--binary', 'HEAD'], cwd=ROOT, capture_output=True, check=True).stdout
    dependencies = []
    for name in ('p1-2-flow-contracts', 'p1-3-flow-compiler', 'p1-4-flow-store-adapter',
                 'p2-1-learning-scope', 'p2-2-page-observation', 'p2-3-interaction-trace',
                 'p2-4-learning-bundle', 'p3-1-draft-generator', 'p3-2-flow-abstraction',
                 'p3-3-layered-validation', 'p3-4-knowledge-publication',
                 'p5-1-knowledge-export', 'p5-2-knowledge-import'):
        base = ROOT.parent / name
        assert base.is_dir()
        files = [{'path': str(p), 'sha256': sha(p)} for p in sorted(base.iterdir())
                 if p.is_file() and p.suffix in {'.py', '.json'}]
        dependencies.append({'root': str(base), 'files': files,
            'digest': hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()})
    gateway = Path('C:/Users/zz/Documents/ChatGPT/毕设/model-gateway')
    files = [{'path': str(gateway / name), 'sha256': sha(gateway / name)} for name in (
        'intent_bridge.py', 'compiler.py', 'contracts.py', 'selection_deadline.py',
        'deadline_remote.py', 'paid_budget.py', 'win_credentials.py')]
    dependencies.append({'root': str(gateway), 'scope': 'Direct gateway imports; credential adapter source only, no credential value',
        'files': files, 'digest': hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest()})
    return {'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
        'branch': subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT).decode().strip(),
        'commit_status': 'UNCOMMITTED_CANDIDATE_NOT_MERGED',
        'tracked_dirty_diff_sha256': hashlib.sha256(tracked_diff).hexdigest(),
        'all_source_digest': hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'source_files_including_untracked': rows, 'original_execution_core': originals,
        'read_only_predecessor_and_gateway_source_snapshots': dependencies,
        'apk': {'path': apk.relative_to(ROOT).as_posix(), 'sha256': sha(apk), 'bytes': apk.stat().st_size,
            'version_code': 93, 'version_name': '0.55-flow-product-wireup', 'signature_command': command,
            'signature_evidence': 'evidence/final-delivery-r15/apk-signature.txt',
            'release_status': 'DEBUG_LAB_ONLY_NOT_PRODUCTION_RELEASE'}, 'deployment': deployment}


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    phone, target = cases(PHONE), cases(TARGET)
    restoration = read('evidence/final-restoration-r15/summary.json')
    assert restoration['passed'] and restoration['transition_animation_restored']
    assert all(h['passed'] and not h['probe_health']['busy'] for h in restoration['hosts'])
    regression = read('evidence/final-local-regression-r15/summary.json')
    assert all(r['passed'] for r in regression)
    for host in ('R5CW134LLBZ', 'emulator-5556'):
        row = read('evidence/g1-' + host + '-r15/summary.json')
        assert row['passed'] == row['executed'] == row['planned'] == 11
        assert row['wrong_action'] == row['false_success'] == 0
    save('current-cases.json', {'phone': phone, 'emulator': target})
    save('cost-ledger-index.json', costs())
    save('freeze.json', freeze())
    fields = {'FLOW_ANDROID_WIREUP': 'PASS_SCOPED_BOTH_11_OF_11_TEST_FIXTURE',
        'P3_REAL_GENERATION': 'ASSISTED_1_CANDIDATE_FROM_2_REAL_REQUESTS',
        'P3_DEVICE_VALIDATION': 'PASS_SCOPED_8_OF_8_V93_R7_NOT_R15',
        'P3_PUBLISHED_FLOW_COUNT': 1, 'P4_REAL_NL_USE': 'PHONE_8_OF_8_EXPECTED_4_OF_4_POSITIVE',
        'P4_CROSS_SESSION_REUSE': 'PHONE_PASS_1_OF_1_EMULATOR_FAIL_0_OF_1',
        'P5_REAL_PACKAGE_EXPORT_IMPORT': 'PASS_SCOPED_ONE_REAL_G2_PACKAGE',
        'P5_TARGET_DEVICE_REUSE': 'PARTIAL_EMULATOR_1_OF_3_POSITIVE_3_OF_5_EXPECTED',
        'AUTOMATIC_OR_ASSISTED': 'DOCUMENTATION_ASSISTED_GENERATION_PLUS_ONE_METADATA_REPAIR; NO_MANUAL_BINDING_OR_REDEMONSTRATION',
        'KNOWLEDGE_REUSE_BENEFIT': 'NOT_DEMONSTRATED', 'TRAINING_REDUCTION': 'NOT_EVALUATED',
        'REAL_TEACHER_APP': 'NOT_TESTED', 'PHYSICAL_PAD': 'NOT_TESTED',
        'REGRESSION': 'PASS_LISTED_CHANNELS_NOT_USER_TASK_SUCCESS_RATE', 'RESTORATION': 'PASS_EXPLICIT_SCOPE_NEW_APK_AND_KNOWLEDGE_RETAINED',
        'P3_FORMAL_ACCEPTANCE': 'PARTIAL_NOT_FULL_PROTOCOL_EXECUTED',
        'P4_FORMAL_ACCEPTANCE': 'PARTIAL_NOT_FULL_PROTOCOL_EXECUTED',
        'P5_FORMAL_ACCEPTANCE': 'PARTIAL_TARGET_TIMEOUT_AND_CROSS_SESSION_FAILURE',
        'OVERALL': 'PARTIAL', 'READY_FOR_FULL_ACCEPTANCE_OR_SHOWROOM_RELEASE': 'NO',
        'remaining_blockers': ['Emulator full Flow exceeds unchanged 8-second native deadline in 2/3 positive cases, including fresh-process reuse.',
            'One documentation-assisted Flow; unassisted generation and broad P3/P4/P5 original acceptance matrices not completed.',
            'No matched cold/warm benefit study, new-user training study, teacher App or physical Pad execution.']}
    save('gates.json', fields)
    paths = [p for p in sorted((ROOT / 'evidence').rglob('*')) if p.is_file() and OUT not in p.parents]
    save('evidence-index.json', {'sealed_at_utc': datetime.now(timezone.utc).isoformat(),
        'files': [{'path': p.relative_to(ROOT).as_posix(), 'sha256': sha(p), 'bytes': p.stat().st_size} for p in paths],
        'notes': 'Existing raw evidence indexed, including old failures. Index sealing is not a new test batch or formal acceptance.'})
    print(json.dumps({'gates': fields, 'cost_attempts': costs()['total_request_attempts_in_this_candidate_evidence'],
                      'evidence_files': len(paths)}, ensure_ascii=False))


if __name__ == '__main__':
    run()
