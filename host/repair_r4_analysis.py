"""R4 offline evidence reduction / read-only snapshot. Never runs a business task.

Does not import product drivers or inherit R3 mutable output directories.
Artifacts only in this new R4 batch; private binary captures remain gitignored.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
R3 = ROOT / 'evidence/flow-deadline-repair/r3/20261008-r1'
OUT = ROOT / 'evidence/flow-deadline-repair/r4/20261008-r1'
PRIVATE = ROOT / 'private/flow-deadline-repair-r4/20261008-r1'
ADB = Path('D:/python_code/closed-loop-gui-agent/tools/android-sdk/platform-tools/adb.exe')
HOSTS = ('R5CW134LLBZ', 'emulator-5556')
CORES = ('PortableSkillRuntime', 'AccessibilityBindingResolver', 'AccessibilityRangeExecutor', 'PortableSkillCodec')
IDENTITY = frozenset(('task_id', 'task_hash', 'cancellation_token_ref'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_json(path, data):
    path = Path(path)
    if path.exists():
        raise FileExistsError(f'PRESERVE_EXISTING_ARTIFACT: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def compare_plans(a, b):
    # JSON byte canonicalization distinguishes bool/number/null/missing and order.
    enc = lambda x: json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    aa = {k: v for k, v in a.items() if k not in IDENTITY}
    bb = {k: v for k, v in b.items() if k not in IDENTITY}
    diff = [k for k in sorted(set(aa) | set(bb)) if k not in aa or k not in bb or enc(aa[k]) != enc(bb[k])]
    ids = [k for k in sorted(IDENTITY) if (k in a) != (k in b) or enc(a.get(k)) != enc(b.get(k))]
    return {'semantic_verdict': 'DIFFERENT' if diff else 'EQUIVALENT', 'semantic_differences': diff,
            'identity_differences': ids, 'normalized_a_sha256': sha(enc(aa).encode()),
            'normalized_b_sha256': sha(enc(bb).encode()), 'ignored_fields': sorted(IDENTITY),
            'does_not_establish_entry_parity': True}


def interval_union_ms(intervals, clip=None):
    work = []
    if clip is not None and clip[1] < clip[0]:
        raise ValueError('INVALID_CLIP')
    for start, end in intervals:
        if end < start:
            raise ValueError('INVALID_MONOTONIC_INTERVAL')
        if clip is not None:
            start, end = max(start, clip[0]), min(end, clip[1])
        if end > start:
            work.append((start, end))
    work.sort()
    total = 0
    if work:
        left, right = work[0]
        for start, end in work[1:]:
            if start > right:
                total += right-left
                left, right = start, end
            else:
                right = max(right, end)
        total += right-left
    return total/1_000_000


def reduce_timing(result):
    timing = result.get('timing', {})
    if timing.get('clock') != 'elapsedRealtimeNanos':
        raise ValueError('UNSUPPORTED_CLOCK_DOMAIN')
    spans = timing.get('spans', [])
    launch = result.get('launch_timing', {})
    deadline = result.get('task_deadline_ms', timing.get('deadline_elapsed_ms'))
    t0 = launch.get('task_started_ms')
    runtime = result.get('latency', {}).get('runtime_ms')
    launch_ms = result.get('latency', {}).get('launch_wait_ms')
    final = [s for s in spans if s['phase'] in ('FINAL', 'observe.FINAL')]
    calls = [s for s in spans if s['phase'].lower().startswith('call.')]
    guards = [s for s in spans if s['phase'] == 'guard.local_knowledge_bytes']
    iv = lambda ss: [(s['start_ns'], s['end_ns']) for s in ss]
    actions = result.get('execution_actions', [])
    first = min((a['ms'] for a in actions if 'ms' in a), default=None)
    queue = 'NOT_MEASURED'
    if 'worker_started_ms' in launch and 'worker_dispatch_requested_ms' in launch:
        queue = launch['worker_started_ms'] - launch['worker_dispatch_requested_ms']
    success = result.get('final_status') in ('SUCCESS', 'NO_ACTION_REQUIRED')
    return {'native_t0_elapsed_ms': t0, 'deadline_elapsed_ms': deadline, 'native_runtime_ms': runtime,
            'remaining_at_launch_wait_sample_ms': 'NOT_MEASURED' if launch_ms is None else 8000-launch_ms,
            'exact_window_ready_remaining_ms': 'NOT_MEASURED',
            'launch_wait_sample_caveat': 'after DeviceContext.capture and runtime construction; not exact readiness instant',
            'first_input_elapsed_ms': first,
            'remaining_before_first_input_ms': 'NOT_REACHED' if first is None else deadline-first,
            'input_floor_ms': 500, 'input_floor_met': None if first is None else deadline-first >= 500,
            'remaining_before_flow_final_ms': 'NOT_REACHED' if not final else deadline-min(s['start_ns'] for s in final)/1e6,
            'queue_ms': queue,
            'completion_slack_ms': 8000-runtime if success else None,
            'deadline_overrun_ms': max(0, runtime-8000),
            'natural_complete_duration_ms': runtime if success else 'NOT_MEASURED',
            'call_union_ms': interval_union_ms(iv(calls)),
            'published_guard_count': len(guards), 'published_guard_union_ms': interval_union_ms(iv(guards)),
            'published_guard_inside_calls_union_ms': sum(interval_union_ms(iv(guards), c) for c in iv(calls)),
            'spans_dropped': timing.get('dropped'), 'marks_dropped': timing.get('marks_dropped'),
            'sdk_id_lookup_count': 'NOT_MEASURED', 'sdk_refresh_count': 'NOT_MEASURED',
            'flow_observation_count': len(result.get('observations', [])),
            'flow_final_reached': bool(final), 'final_status': result.get('final_status')}


def check_integrity():
    expected = read(R3/'evidence-index.json')['files']
    errors = []
    for relative, digest in expected.items():
        p = R3/relative
        if not p.is_file() or sha(p.read_bytes()) != digest:
            errors.append(relative)
    old_source = read(R3/'final-source-hashes.json')
    current = {}
    for relative in old_source:
        p = ROOT/relative
        current[relative] = sha(p.read_bytes()) if p.is_file() else None
    drift = [k for k in old_source if old_source[k] != current[k]]
    core_hashes = {name: sha((ROOT/f'native/app/src/main/java/edu/sydney/probe/{name}.java').read_bytes()) for name in CORES}
    freeze = read(R3/'candidate-v103/freeze.json')
    apk = Path(freeze['apk'])
    data = {'old_evidence_count': len(expected), 'old_evidence_mismatches': errors,
            'r3_source_file_count': len(old_source), 'source_drift_vs_r3_final': drift,
            'source_hashes': current, 'protected_core_sha256': core_hashes,
            'd103_apk_sha256': sha(apk.read_bytes()) if apk.exists() else None,
            'd103_apk_matches_freeze': apk.exists() and sha(apk.read_bytes()) == freeze['apk_sha256'],
            'r3_core_proposal_sha256': sha((R3/'core_change_request.md').read_bytes())}
    if errors:
        raise ValueError(f'R3_EVIDENCE_INTEGRITY_FAILED: {errors}')
    return data


def analyze():
    write_json(OUT/'source-and-evidence-integrity-before.json', check_integrity())
    rows = []
    paths = sorted((R3/'confirmation-r2/normal/reproduction-v103').glob('*.json'))
    paths += sorted((R3/'real_nl/final-phone').glob('*.json'))
    paths += sorted((R3/'real_nl/final-emulator').glob('*.json'))
    for path in paths:
        d = read(path)
        if 'case' not in d or not ('result' in d or 'ui' in d):
            continue
        result = d.get('result') or d.get('ui', {}).get('result')
        # Clarify/rejected/cancel cases may never reach a timed native receipt.
        if not result or result.get('timing', {}).get('clock') != 'elapsedRealtimeNanos':
            rows.append({'source': str(path), 'source_sha256': sha(path.read_bytes()), 'case': d['case'],
                         'host': d['host'], 'timing': 'NOT_REACHED_OR_NOT_RECORDED', 'final_status': d.get('final_status')})
            continue
        plan = d.get('plan') or d['ui']['selection']['plan']
        model = d.get('model_evidence')
        if model and sha(Path(model['path']).read_bytes()) != model['sha256']:
            raise ValueError('MODEL_AUDIT_DIGEST')
        rows.append({'source': str(path), 'source_sha256': sha(path.read_bytes()), 'case': d['case'],
                     'rep': d.get('rep'), 'host': d['host'], 'mode': result.get('mode'), 'channel': d['channel'],
                     'initial': d['before'], 'process_session': result.get('process_session'),
                     'request_id': result.get('request_id'), 'task_id': result.get('task_id'),
                     'flow_hash': result.get('flow_hash'), 'plan': plan,
                     'timing': reduce_timing(result), 'assessment': d['assessment'],
                     'final_status': result.get('final_status'), 'completion_boundary': result.get('completion_boundary'),
                     'model_evidence': model,
                     'work_counts': {'start_activity': 1 if result.get('launch_timing', {}).get('start_activity_started_ms') else 'NOT_MEASURED',
                                     'flow_observations': len(result.get('observations', [])),
                                     'span_phase_counts': {phase: sum(s['phase'] == phase for s in result['timing']['spans'])
                                                           for phase in sorted({s['phase'] for s in result['timing']['spans']})}}})
    p = OUT/'entry_parity_matrix.jsonl'
    if p.exists():
        raise FileExistsError(p)
    p.write_text(''.join(json.dumps(x, ensure_ascii=False)+'\n' for x in rows), encoding='utf-8')
    a = read(R3/'confirmation-r2/normal/reproduction-v103/emulator-5556-E2-0.json')
    b = read(R3/'real_nl/final-emulator/new_session.json')
    ra, rb = reduce_timing(a['result']), reduce_timing(b['ui']['result'])
    pair = compare_plans(a['plan'], b['ui']['selection']['plan'])
    # Compare every initial field, ignoring only the per-case identity.
    ai = {k: v for k, v in a['before'].items() if k != 'case_id'}
    bi = {k: v for k, v in b['before'].items() if k != 'case_id'}
    pair.update({'initial_state_and_pending_equal': compare_plans(ai, bi)['semantic_verdict'] == 'EQUIVALENT',
                 'entry_verdict': 'DIFFERENT', 'entry_a': a['result']['mode'], 'entry_b': b['ui']['result']['mode'],
                 'compiled_plan_parity_does_not_equal_full_entry_parity': True,
                 'structured': ra, 'real_new_session': rb,
                 'call_increase_ms': rb['call_union_ms']-ra['call_union_ms'],
                 'increase_not_explained_by_published_guard_in_call_ms': rb['call_union_ms']-ra['call_union_ms']-rb['published_guard_inside_calls_union_ms'],
                 'exclusive_sdk_cost_or_root_cause_claim': False})
    write_json(OUT/'matched_pair_analysis.json', pair)
    print(json.dumps({k: v for k, v in pair.items() if k not in ('structured', 'real_new_session')}, ensure_ascii=False))


def regression():
    modules = ['test_repair_r3_gate', 'test_repair_r3_timing', 'test_repair_scorer',
               'test_repair_r3_confirm', 'test_repair_r3_real_nl', 'test_repair_r3_restore', 'test_repair_r4_analysis']
    out = OUT/'regression'
    out.mkdir(parents=True, exist_ok=True)
    results = []
    for module in modules:
        log = out/(module+'.txt')
        if log.exists():
            raise FileExistsError(log)
        cmd = [sys.executable, '-X', 'utf8', '-m', 'unittest', '-v', module]
        start = time.monotonic_ns()
        p = subprocess.run(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        log.write_bytes(p.stdout)
        results.append({'module': module, 'argv': cmd, 'exit_code': p.returncode,
                        'duration_ms': (time.monotonic_ns()-start)/1e6, 'log': str(log), 'log_sha256': sha(p.stdout)})
        print(module, 'PASS' if p.returncode == 0 else 'FAIL', flush=True)
        if p.returncode != 0:
            break
    write_json(out/'results.json', results)
    if any(x['exit_code'] for x in results) or len(results) != len(modules):
        raise SystemExit(1)


def capture(phase):
    out = PRIVATE/phase
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    def command(args, limit=45):
        p = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=limit)
        if p.returncode:
            raise ValueError(f'READONLY_COMMAND_FAILED: {args[:5]} {p.stderr.decode(errors="replace")[:150]}')
        return p.stdout
    devices = command([str(ADB), 'devices', '-l']).decode()
    (out/'devices.txt').write_text(devices, encoding='utf-8')
    data = {'time_utc': datetime.now(timezone.utc).isoformat(), 'kind': 'READ_ONLY_NO_HEALTH_BROADCAST',
            'product_installs': 0, 'business_tasks': 0, 'model_calls': 0, 'hosts': {}}
    for host in HOSTS:
        def adb(*args):
            return command([str(ADB), '-s', host, *args])
        adb('get-state')
        folder = out/host; folder.mkdir()
        env = {}
        for name, args in {
            'size': ('shell', 'wm', 'size'), 'density': ('shell', 'wm', 'density'),
            'font_scale': ('shell', 'settings', 'get', 'system', 'font_scale'),
            'rotation': ('shell', 'settings', 'get', 'system', 'user_rotation'),
            'auto_rotate': ('shell', 'settings', 'get', 'system', 'accelerometer_rotation'),
            'enabled_services': ('shell', 'settings', 'get', 'secure', 'enabled_accessibility_services'),
            'accessibility_enabled': ('shell', 'settings', 'get', 'secure', 'accessibility_enabled'),
            'android_version': ('shell', 'getprop', 'ro.build.version.release'),
            'model': ('shell', 'getprop', 'ro.product.model'),
            'qemu': ('shell', 'getprop', 'ro.kernel.qemu')}.items():
            env[name] = adb(*args).decode(errors='replace').strip()
        (folder/'accessibility.txt').write_bytes(adb('shell', 'dumpsys', 'accessibility'))
        (folder/'activities.txt').write_bytes(adb('shell', 'dumpsys', 'activity', 'activities'))
        processes = adb('shell', 'ps', '-A').decode(errors='replace')
        (folder/'processes.txt').write_text(processes, encoding='utf-8')
        packages = {}
        for pkg in ('edu.sydney.probe', 'edu.sydney.parameterroom'):
            dump = adb('shell', 'dumpsys', 'package', pkg).decode(errors='replace')
            (folder/(pkg+'.package.txt')).write_text(dump, encoding='utf-8')
            path = adb('shell', 'pm', 'path', pkg).decode().strip()
            if not path.startswith('package:/data/app/') or '\n' in path:
                raise ValueError('APK_PATH_NOT_SINGLE_BASE')
            apk = adb('exec-out', 'cat', path[len('package:'):])
            (folder/(pkg+'.apk')).write_bytes(apk)
            archive = adb('exec-out', 'run-as', pkg, 'tar', '-cf', '-', 'files', 'shared_prefs')
            (folder/(pkg+'.tar')).write_bytes(archive)
            with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
                files = {m.name: sha(tar.extractfile(m).read()) for m in tar.getmembers() if m.isfile()}
            packages[pkg] = {'apk_sha256': sha(apk), 'file_digests': files, 'archive_sha256': sha(archive),
                             'version': [l.strip() for l in dump.splitlines() if 'versionCode=' in l or 'versionName=' in l]}
            print(host, pkg, packages[pkg]['version'], sha(apk), flush=True)
        data['hosts'][host] = {'environment': env, 'packages': packages,
                               'probe_process': [l for l in processes.splitlines() if l.strip().endswith(' edu.sydney.probe')],
                               'target_process': [l for l in processes.splitlines() if l.strip().endswith(' edu.sydney.parameterroom')],
                               'ready_busy': 'NOT_MEASURED_NO_READONLY_LIVE_ENDPOINT_USED'}
    ps = command(['powershell', '-NoProfile', '-Command',
                  "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match '[f]low_bridge\\.py' } | Select-Object ProcessId,ParentProcessId,Name | ConvertTo-Json -Compress"])
    (out/'gateway-processes.json').write_bytes(ps)
    data['gateway_processes'] = json.loads(ps.decode('utf-8-sig')) if ps.strip() else []
    ports = command(['powershell', '-NoProfile', '-Command',
                     "Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,OwningProcess | ConvertTo-Json -Compress"])
    (out/'listening-ports.json').write_bytes(ports)
    data['listening_ports_sha256'] = sha(ports)
    write_json(OUT/f'现场只读回读-{phase}.json', data)


def seal():
    before, after = read(OUT/'现场只读回读-before.json'), read(OUT/'现场只读回读-after.json')
    check = {}
    for host in HOSTS:
        a, b = before['hosts'][host], after['hosts'][host]
        check[host] = {'environment_equal': a['environment'] == b['environment'],
                       'apk_equal': {p: a['packages'][p]['apk_sha256'] == b['packages'][p]['apk_sha256'] for p in a['packages']},
                       'app_file_content_equal': {p: a['packages'][p]['file_digests'] == b['packages'][p]['file_digests'] for p in a['packages']},
                       'probe_process_equal': a['probe_process'] == b['probe_process'],
                       'target_process_equal': a['target_process'] == b['target_process'],
                       'live_ready_busy': b['ready_busy']}
    write_json(OUT/'restoration/read-only-preservation.json', {'kind': 'NO_RESTORE_NO_MUTATION_BY_THIS_BATCH',
               'hosts': check, 'gateway_before': before['gateway_processes'], 'gateway_after': after['gateway_processes'],
               'global_ports_observed_only_not_restored': True})
    write_json(OUT/'source-and-evidence-integrity-after.json', check_integrity())
    print(json.dumps(check, ensure_ascii=False))


def details():
    rows = [json.loads(line) for line in (OUT/'entry_parity_matrix.jsonl').read_text(encoding='utf-8').splitlines()]
    breakdown = []
    for row in rows:
        if not isinstance(row['timing'], dict):
            continue
        source = read(row['source'])
        result = source.get('result') or source['ui']['result']
        spans = result['timing']['spans']
        calls = [s for s in spans if s['phase'] == 'call.set_brightness']
        if not calls:
            continue
        if len(calls) != 1:
            raise ValueError('THIS_FOUR_STEP_REDUCER_REQUIRES_ONE_CALL')
        call = calls[0]; clip = (call['start_ns'], call['end_ns'])
        phases = ['guard.current_root', 'guard.legacy_current_bytes', 'guard.local_knowledge_bytes']
        union = interval_union_ms([(s['start_ns'], s['end_ns']) for s in spans if s['phase'] in phases], clip)
        breakdown.append({'source': row['source'], 'case': row['case'], 'host': row['host'], 'rep': row['rep'],
                          'call_ms': (clip[1]-clip[0])/1e6,
                          'inside_call_ms': {p: interval_union_ms([(s['start_ns'], s['end_ns']) for s in spans if s['phase'] == p], clip) for p in phases},
                          'known_guard_union_in_call_ms': union, 'not_covered_by_these_guards_ms': (clip[1]-clip[0])/1e6-union,
                          'uncovered_is_not_exclusive_sdk_cost': True})
    write_json(OUT/'guard_interval_breakdown.json', breakdown)
    lines = ['# R3 同候选时间复算（非 R4 新设备成绩）', '',
             '单位 ms。P95 若使用，采用 nearest-rank；本表逐例保留，未混合成功与超时推算自然完成时间。', '',
             '|宿主/样本|原生终态耗时|launch_wait 取样后余量*|首业务输入前余量|Flow FINAL 前余量|状态|',
             '|---|---:|---:|---:|---:|---|']
    for row in rows:
        t = row['timing']
        if not isinstance(t, dict):
            continue
        label = ('模拟器' if row['host'].startswith('emulator') else '真机')+'/'+row['case']
        if row.get('rep') is not None:
            label += '/'+str(row['rep'])
        fmt = lambda x: f'{x:.3f}' if isinstance(x, (int, float)) else str(x)
        lines.append('|'+label+'|'+ '|'.join(fmt(t[k]) for k in ('native_runtime_ms', 'remaining_at_launch_wait_sample_ms', 'remaining_before_first_input_ms', 'remaining_before_flow_final_ms'))+'|'+row['final_status']+'|')
    lines += ['', '* launch_wait 在 DeviceContext.capture 与 runtime 构造之后取样，不是精确 ready 时刻。精确 ready 后余量 = NOT_MEASURED。',
              '同任务仅相减 elapsedRealtime 系时钟；模型和主机墙钟未加入原生 8 秒。FINAL 缺失 = NOT_REACHED，不能填 0。', '',
              '## CALL 中已知 guard 的区间并集', '',
              '|样本|CALL|Root guard|发布知识 guard|旧批准 guard|三类 guard 并集|未被三类 guard 覆盖|', '|---|---:|---:|---:|---:|---:|---:|']
    for b in breakdown:
        if b['host'] == 'emulator-5556' and ((b['case'] == 'E2' and b['rep'] == 0) or b['case'] in ('explicit', 'new_session')) or b['host'] == HOSTS[0] and b['case'] == 'new_session':
            v = b['inside_call_ms']
            lines.append('|'+('模拟器' if b['host'].startswith('emulator') else '真机')+'/'+b['case']+'|'+ '|'.join(f'{n:.3f}' for n in (b['call_ms'], v['guard.current_root'], v['guard.local_knowledge_bytes'], v['guard.legacy_current_bytes'], b['known_guard_union_in_call_ms'], b['not_covered_by_these_guards_ms']))+'|')
    lines += ['', '未覆盖部分包括核心 SDK/逻辑、输入、等待及调度等，不能直接称为“SDK 独占时间”。嵌套区间不得相加。',
              '匹配 E2-0 → 真实 new_session：CALL 增加 1196.8365ms；发布知识 guard 在 CALL 内 529.2142ms，仍有 667.6223ms 未由该差异解释。',
              '失败例 guard 48 次/664.6039ms；普通真实成功例 65 次/339.7286ms。次数不是删除检查的依据。', '',
              '## 失败例剩余预算与完成边界', '',
              '- t0=149139606，deadline=149147606，均为该任务 elapsedRealtime 毫秒。',
              '- worker 排队=2ms；launch_wait=4164ms，对应余量3836ms（代理取样）。',
              '- 第一次业务输入149146230，余量1376ms，满足原500ms底线。只有一次 SET_PROGRESS。',
              '- 149147198观察到目标60，但仅 TARGET_ONLY，不是完整核验。',
              '- child FULL于149147605记录；child verification=false/UNCONFIRMED；不能代替整条 Flow FINAL。',
              '- AFTER/read_after/ASSERT/Flow FINAL未到达；最后SERVICE_RECEIPT_READY=149148081，越界475ms，正确BUDGET_EXCEEDED。',
              '- flow JSON=37.3283ms；服务JSON=95.5189ms；事件范围恢复=167.5572ms。均在原合同内，不能移出计时。',
              '- 模型3156.5439ms、编译198.4236ms在原生t0之前，分账；不能用它们解释原生8秒耗尽。',
              '- 8475ms是被截止约束后的终态，不是自然完整成功耗时；不能声称“成功只差475ms”。']
    path = OUT/'timing_comparison.md'
    if path.exists():
        raise FileExistsError(path)
    path.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    freeze = read(R3/'candidate-v103/freeze.json')
    real_freeze = read(R3/'real-nl-freeze.json')
    model_source = read(R3/'real_nl/final-emulator/fresh-session/model-audit/a1fb792beefc4eafa1a889825f11bb89.json')
    manifest = {'batch_id': 'flow-r4-20261008-r1', 'phase': 'DIAGNOSIS_ONLY_CORE_APPROVAL_PENDING',
                'head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                'dirty_worktree_preserved': True, 'product_modified': False, 'model_calls_this_batch': 0, 'device_business_tasks_this_batch': 0,
                'user_contract': {'path': 'C:/Users/zz/Downloads/flow_timeout_r4_new_session_diagnosis_repair_prompt.md',
                                  'sha256': sha(Path('C:/Users/zz/Downloads/flow_timeout_r4_new_session_diagnosis_repair_prompt.md').read_bytes())},
                'r3_summary': {'path': 'C:/Users/zz/Documents/ChatGPT/毕设/tasks/flow-deadline-repair/continuation-r3-report.md',
                               'sha256': sha(Path('C:/Users/zz/Documents/ChatGPT/毕设/tasks/flow-deadline-repair/continuation-r3-report.md').read_bytes()),
                               'expected_sha256': '68570c7c612d4341066124fb0fa93725ef974d1dcff13d660bbbace9576f00ff'},
                'native_budget_ms': 8000, 'protected_floor_ms': 500, 'stable_ms': 200, 'maximum_stable_gap_ms': 400,
                'd103_apk_sha256': freeze['apk_sha256'], 'flow_hash': freeze['flow_hash'],
                'r3_model_config_reference_only': {k: real_freeze[k] for k in ('model','temperature','reasoning','max_output_tokens','prompt_sha256','knowledge')},
                'r3_actual_failed_model': model_source['model']['returned_model'],
                'source_and_scorer_freeze': str(OUT/'source-and-evidence-integrity-before.json'),
                'new_offline_tools': {p.name: sha(p.read_bytes()) for p in (ROOT/'repair_r4_analysis.py', ROOT/'test_repair_r4_analysis.py')},
                'supersedes_no_old_results': True}
    write_json(OUT/'manifest.json', manifest)
    print('Details generated; no device tasks, product edits or model requests.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('analyze', 'regression', 'snapshot', 'seal', 'details'))
    parser.add_argument('--phase', choices=('before', 'after'))
    args = parser.parse_args()
    if args.action == 'snapshot':
        if not args.phase:
            parser.error('--phase required')
        capture(args.phase)
    else:
        globals()[args.action]()
