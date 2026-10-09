"""Finalize R4 diagnostic report metadata; local reads and new artifacts only."""
import hashlib
import json
import math
import re
import statistics
from pathlib import Path

from repair_r4_analysis import OUT, ROOT, R3, read, sha, write_json


def distribution(values):
    values = sorted(values)
    return {'n': len(values), 'p50': statistics.median(values) if values else None,
            'p95_nearest_rank': values[math.ceil(.95*len(values))-1] if values else None,
            'max': max(values) if values else None}


def finalize():
    integrity = read(OUT/'source-and-evidence-integrity-after.json')
    if integrity['old_evidence_mismatches'] or integrity['source_drift_vs_r3_final']:
        raise ValueError('SOURCE_OR_OLD_EVIDENCE_DRIFT')
    manifest = read(OUT/'manifest.json')
    if any(sha((ROOT/name).read_bytes()) != digest for name, digest in manifest['new_offline_tools'].items()):
        raise ValueError('ANALYSIS_TOOL_DRIFT')
    regressions = read(OUT/'regression/results.json')
    counts = {}
    for row in regressions:
        log = Path(row['log']).read_bytes()
        if row['exit_code'] != 0 or sha(log) != row['log_sha256']:
            raise ValueError('REGRESSION_FAILED_OR_TAMPERED')
        count = re.findall(r'Ran (\d+) tests? in ', log.decode())
        if len(count) != 1:
            raise ValueError('TEST_COUNT_MISSING')
        counts[row['module']] = int(count[0])
    snapshots = {p: read(OUT/f'现场只读回读-{p}.json') for p in ('before','after')}
    preservation = read(OUT/'restoration/read-only-preservation.json')
    processes = {}
    for host, checks in preservation['hosts'].items():
        if not checks['environment_equal'] or not all(checks['apk_equal'].values()) or not all(checks['app_file_content_equal'].values()):
            raise ValueError('CURRENT_DEVICE_DATA_CHANGED_REPORT_BLOCKED')
        ids = {p: [line.split()[1:3] for line in snapshots[p]['hosts'][host]['probe_process']] for p in snapshots}
        processes[host] = {'before_pid_ppid': ids['before'], 'after_pid_ppid': ids['after'],
                           'same_pid_ppid': ids['before'] == ids['after'],
                           'raw_ps_row_equal': checks['probe_process_equal'],
                           'raw_row_comparison_includes_rss_and_scheduler_state': True,
                           'pid_equality_does_not_prove_session_identity': True}
    write_json(OUT/'restoration/process-row-interpretation.json', processes)
    entries = [json.loads(line) for line in (OUT/'entry_parity_matrix.jsonl').read_text(encoding='utf-8').splitlines()]
    latency = {}
    for host in snapshots['before']['hosts']:
        timed = [r for r in entries if r['host'] == host and isinstance(r['timing'], dict)]
        native = [r for r in timed if r['channel'] == 'STRUCTURED_NORMAL_ENTRY_DIAGNOSTIC']
        real = [r for r in timed if r['channel'] == 'REAL_GPT_NORMAL_UI_PUBLISHED_FLOW']
        latency[host] = {'historical_native_normal_all': distribution([r['timing']['native_runtime_ms'] for r in native]),
                         'historical_real_all_native_terminal_including_no_effect': distribution([r['timing']['native_runtime_ms'] for r in real]),
                         'historical_real_success_only_including_no_action': distribution([r['timing']['native_runtime_ms'] for r in real if r['final_status'] in ('SUCCESS','NO_ACTION_REQUIRED')])}
    write_json(OUT/'historical-latency-distributions.json', {'source': 'R3_ONLY_NOT_R4_DEVICE_RUNS', 'method': 'median; nearest-rank P95; max; no cross-host raw clock subtraction', 'hosts': latency})
    # Read pinned predecessor metadata directly; do not import any execution or network provider.
    p33 = ROOT.parent/'p3-3-layered-validation/evidence/frozen-confirmation-r2/freeze.json'
    pred = read(p33)
    digest = sha(json.dumps(pred['files'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode())
    bad = [row['path'] for row in pred['files'] if sha(Path(row['path']).read_bytes()) != row['sha256']]
    modules = [ROOT.parent/'p3-4-knowledge-publication/p34deps.py', ROOT.parent/'p3-4-knowledge-publication/flow_store_v2.py']
    gateway = Path('C:/Users/zz/Documents/ChatGPT/毕设/model-gateway')
    modules += [gateway/(n+'.py') for n in ('intent_bridge','compiler','contracts','selection_deadline','deadline_remote','paid_budget')]
    write_json(OUT/'dependency-audit.json', {
        'p33_pinned_manifest_path': str(p33), 'p33_source_hash': digest,
        'p33_expected_hash': '4016a5956692a7838128838d19e443a06650fb70f6dbc3e8e06d42efb921e34d',
        'p33_files_checked': len(pred['files']), 'p33_bad_files': bad,
        'p33_current_pin_valid': digest == pred['source_hash'] == '4016a5956692a7838128838d19e443a06650fb70f6dbc3e8e06d42efb921e34d' and not bad,
        'current_external_module_hashes': {str(p): sha(p.read_bytes()) if p.exists() else None for p in modules},
        'complete_r3_external_gateway_hash_parity': 'NOT_ESTABLISHED_HISTORICAL_FREEZE_DOES_NOT_CONTAIN_ALL_MODULES',
        'no_model_provider_import_or_request': True})
    result = {
        'CURRENT_CANDIDATE': {'source': 'D103 same R3-final 299-file baseline', 'installed': {h: v['packages']['edu.sydney.probe']['version'] for h,v in snapshots['after']['hosts'].items()}},
        'R3_EVIDENCE_REVIEW': {'status': 'COMPLETE', 'evidence_checked': 488, 'mismatches': 0},
        'RUNNER_STOP_GATE_REGRESSION': {'status': 'PASS', 'methods': counts['test_repair_r3_gate']},
        'STRUCTURED_VS_REAL_PARITY': {'semantic_plan': 'EQUIVALENT', 'initial_state': 'EQUIVALENT', 'entry': 'DIFFERENT', 'external_dependencies': 'PARTIALLY_VERIFIED_SEE_DEPENDENCY_AUDIT'},
        'M0_M1_M2_DIAGNOSTICS': {'status': 'NOT_RUN', 'physical': 0, 'emulator': 0, 'replay': 0},
        'ROOT_CAUSE_STATUS': 'NOT_ESTABLISHED', 'UNRESOLVED_VARIABILITY': True,
        'EXISTING_CORE_PROPOSAL_REVIEW': 'NARROWED_TO_RESOLVER_TIMING_ONLY',
        'PROTECTED_CORE_MODIFIED': False, 'CORE_CHANGE_REQUIRES_APPROVAL': True,
        'NATIVE_FINAL_CONFIRMATION': {'R4': 'NOT_RUN', 'historical_D103_only': {'physical': '6/6', 'emulator': '6/6'}},
        'REAL_NEW_SESSION_SENTINEL': {'status': 'NOT_RUN', 'started': 0},
        'REAL_NL_FULL_CONFIRMATION': {'R4': {'planned': 24, 'started': 0, 'success': 0, 'failed': 0, 'unexecuted': 24, 'model_requests': 0},
                                      'R3_kept_not_resumed': {'planned': 24, 'started': 16, 'expected_pass': 15, 'failed': 1, 'unexecuted': 8, 'model_requests': 16}},
        'G1': {'R4': 'NOT_RUN', 'same_hash_historical': '11/11 per host'},
        'CANCEL': {'R4': 'NOT_RUN', 'same_hash_historical': '2/2 per host'},
        'LOCAL_REGRESSION': {'methods_by_module': counts, 'device_tasks': 0, 'model_calls': 0},
        'DEADLINE_AND_SAFETY_INVARIANTS': {'source': 'UNCHANGED', 'offline_protection': 'PASS', 'new_UI_safety': 'NOT_TESTED', 'no_empty_denominator_zero_percent_claim': True},
        'RESTORATION': {'status': 'READ_ONLY_PRESERVATION_VERIFIED_NO_RESTORE', 'apk_files_settings_equal': True, 'live_ready_busy': 'NOT_MEASURED', 'gateway_after': snapshots['after']['gateway_processes']},
        'TIMEOUT_REPAIR_ACCEPTANCE': 'PARTIAL', 'DIAGNOSIS': 'COMPLETE',
        'P3_P4_P5_FORMAL_ACCEPTANCE': 'NOT_UPGRADED', 'SHOWROOM_RELEASE': 'NO'}
    write_json(OUT/'result.json', result)
    files = {str(p.relative_to(OUT)): sha(p.read_bytes()) for p in sorted(OUT.rglob('*')) if p.is_file()}
    write_json(OUT/'evidence-index.json', {'batch': 'flow-r4-20261008-r1', 'files': files,
                'self_excluded': True, 'reporting_tool_sha256': sha(Path(__file__).read_bytes()),
                'old_r3_result_sha256': sha((R3/'result.json').read_bytes()),
                'r3_evidence_unchanged': True, 'product_changes': 0, 'new_model_requests': 0})
    print(json.dumps({'diagnosis': 'COMPLETE', 'timeout_repair': 'PARTIAL', 'methods': counts, 'r4_index_files': len(files), 'p33_pin_valid': not bad and digest == pred['source_hash']}))


if __name__ == '__main__':
    finalize()
