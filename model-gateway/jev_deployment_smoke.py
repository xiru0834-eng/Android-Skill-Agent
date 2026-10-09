"""Verify the installed Jev bridge, not an injected or temporary test server."""
import argparse
import hashlib
import json
import secrets
import statistics
import time
import urllib.request
from pathlib import Path
from named_journey_device import prefs, fixture, library, tap, text, snap, home, PROBE, APP
from named_language_evaluation import catalog
from partial_journey import run as partial_run
from named_journey_execution import run as whole_run
from transfer_run import private
from transfer_terminal_wait import wait_terminal
from workflow_capture import tree
from workflow_experiment import adb, write, ROOT

SERIAL = 'R5CW134LLBZ'
DIRECT = [('执行阅读60', [1, 60, 1, 1]), ('Run LampOnly60.', [1, 60, None, None]),
          ('不要执行阅读60', None), ('Run Reading60 but change brightness to 20%.', None)]
EXECUTIONS = [('whole-zh', whole_run, dict(skill='reading', condition='none', initial=[0, 40, 0, 3]), '执行阅读60'),
              ('partial-en', partial_run, dict(skill='lamp', condition='none', repeat=0, initial=[0, 40, 1, 3]), 'Turn on only the reading lamp at sixty percent. Keep the fan unchanged.'),
              ('partial-zh', partial_run, dict(skill='fan', condition='none', repeat=0, initial=[1, 80, 0, 3]), '只打开风扇并设为低档，阅读灯保持不变。')]
NEGATIVES = ['执行阅读60，但亮度改为20%。', 'Do not run LampOnly60.']


def verify_execution(row, *, partial):
    assert row['actual_success'] and row['confirmed_success'] and not row['false_success']
    assert not row['non_target_violation'] and row['post_terminal_inputs'] == 0 and row['route']['valid']
    if partial:
        assert row['extraInputs'] == row['unexpectedInputs'] == row['afterDeadlineInputs'] == 0
    else:
        # Missing counters must fail, not silently default to a safe zero.
        assert all(row['inputSafety'][key] == 0 for key in ('afterDeadlineInputs', 'unexpectedIds', 'extraInputs'))


def verify_session(session,selector):
    assert selector in ('jev','routed')
    assert session['selector']==selector and session['port']==(8767 if selector=='routed' else 8766)


def reaudit(out):
    from transfer_audit import evaluate
    from startup_audit import input_safety
    from recovery_evidence import audit_route
    from partial_journey import score_case
    rows = []
    for name, operator, _, _ in EXECUTIONS:
        folder = out/name
        load = lambda file: json.loads((folder/file).read_text(encoding='utf-8'))
        case, skill, oracle = load('case.json'), load('skill.json'), load('oracle.json')
        terminal, audits, journal, before = load('terminal.json'), load('audit.json'), load('journal.json'), load('before.json')
        if operator is partial_run:
            row = score_case(case, skill, oracle, terminal, audits, journal, before)
        else:
            row = evaluate(oracle, terminal, skill['finalGoals'], audits, case_id=before['caseId'], run_id=terminal['runId'])
            row.update(route=audit_route(terminal, skill), inputSafety=input_safety(oracle, terminal, skill))
        verify_execution(row, partial=operator is partial_run)
        rows.append(dict(name=name, **row))
    write(out/'strict-reaudit.json', dict(passed=len(rows), additionalApiRequests=0, rows=rows,
        correction='Use exact inputSafety field names; recomputed from preserved oracle, journal and audits.',
        amendedSourceSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()))
    print('PASS strict independent reaudit of '+str(len(rows))+' executions; zero new API calls')


def main(out,selector='jev'):
    out.mkdir(parents=True, exist_ok=False)
    session = json.loads((ROOT/('runtime/selector-session/'+selector+'.json')).read_text(encoding='utf-8-sig'))
    verify_session(session,selector);port=session['port']
    assert any(line.split()[-2:] == ['tcp:8765', 'tcp:'+str(port)] for line in adb(SERIAL, 'reverse', '--list').splitlines())
    state = prefs(SERIAL)
    old = private(SERIAL, APP, 'workflow-oracle.json')
    saved = old['events'][-1]['saved'] if old.get('events') else old['initial']
    skills = catalog(SERIAL)
    token = prefs(SERIAL, 'language_connection')['pairing']  # Memory only; never evidence.
    write(out/'protocol.json', dict(kind='DEPLOYED_SERVICE_SMOKE', pid=session['pid'], selector=selector,
        direct=DIRECT, executions=[dict(name=n, case=c, text=t) for n, _, c, t in EXECUTIONS], negatives=NEGATIVES,
        expectedBridgeRequests=9, expectedRealRequests=6 if selector=='routed' else 9, retries=0, phoneBudgetMs=30000, postAuditSeconds=5,
        sourceHashes={name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                      for name in ['jev_selection.py', 'selection_routing.py', 'start_teaching_bridge.py', 'catalog_uniqueness.py', 'jev_deployment_smoke.py']}))
    write(out/'library-before.json', json.loads(state['library']))
    direct_rows, executed, negative_rows = [], [], []
    try:
        for command, goal in DIRECT:
            before = prefs(SERIAL)
            oracle = private(SERIAL, APP, 'workflow-oracle.json')
            body = dict(request_id=secrets.token_hex(16), text=command, skills=skills)
            request = urllib.request.Request('http://127.0.0.1:'+str(port)+'/v1/skill-selections',
                data=json.dumps(body, ensure_ascii=False).encode(),
                headers={'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
            started = time.perf_counter()
            with urllib.request.urlopen(request, timeout=55) as response:
                selection = json.loads(response.read(32769))
            elapsed = (time.perf_counter()-started)*1000
            expected = next((s['id'] for s in skills if s['finalGoals'] == goal), None) if goal else None
            assert selection['request_id'] == body['request_id']
            assert (selection['status'] == 'invoke' and selection['skill_id'] == expected) if expected else (selection['status'] in ('clarify', 'reject') and selection['skill_id'] is None)
            assert prefs(SERIAL).get('result') == before.get('result') and private(SERIAL, APP, 'workflow-oracle.json') == oracle
            direct_rows.append(dict(text=command, selection=selection, ms=round(elapsed, 2), noExecution=True))
            write(out/'direct-results.json', direct_rows)
            print('PASS deployed API: '+selection['status'], flush=True)
        for name, operator, case, command in EXECUTIONS:
            row = operator(SERIAL, case, out/name, command)
            verify_execution(row, partial=operator is partial_run)
            executed.append(dict(name=name, **row))
            write(out/'execution-results.json', executed)
            print('PASS phone workflow: '+name, flush=True)
        for index, command in enumerate(NEGATIVES):
            library(SERIAL)
            before = prefs(SERIAL)
            oracle = private(SERIAL, APP, 'workflow-oracle.json')
            text(SERIAL, 'libraryInput', command)
            tap(SERIAL, 'libraryChoose')
            end = time.monotonic()+55
            while time.monotonic() < end:
                ui = tree(SERIAL)
                assert not any(n.get('resource-id') == 'android:id/button1' for n in ui.iter('node'))
                ready = any(n.get('resource-id') == PROBE+':id/libraryChoose' and n.get('enabled') == 'true' for n in ui.iter('node'))
                message = next((n.get('text', '') for n in ui.iter('node') if n.get('resource-id') == PROBE+':id/libraryStatus'), '')
                if ready and any(s in message for s in ('请补充', '该请求不在')):
                    break
                time.sleep(.3)
            else:
                raise RuntimeError('No successful non-invoke response; unavailable is not rejection')
            after = prefs(SERIAL)
            assert after.get('result') == before.get('result') and after.get('approved') == before.get('approved')
            assert private(SERIAL, APP, 'workflow-oracle.json') == oracle
            snap(SERIAL, out/('negative-'+str(index)+'.png'))
            negative_rows.append(dict(text=command, noConfirmation=True, noExecution=True, oracleExactUnchanged=True))
            write(out/'negative-results.json', negative_rows)
            print('PASS phone non-invoke', flush=True)
        write(out/'summary.json', dict(directPassed=len(direct_rows), executionsPassed=len(executed), negativesPassed=len(negative_rows),
            bridgeRequests=9, expectedRemoteRequests=6 if selector=='routed' else 9, directHttpP50ms=statistics.median(r['ms'] for r in direct_rows), scope='deployment smoke, not generalization accuracy'))
    except Exception as error:
        write(out/'failure.json', dict(type=type(error).__name__, reason=str(error)))
        raise
    finally:
        # Restore selected approval through normal UI, not private writes.
        if prefs(SERIAL).get('approved') != state.get('approved'):
            entries = json.loads(state['library'])
            found = [(i, e) for i, e in enumerate(entries) if e['skill'] == json.loads(state['approved'])]
            assert len(found) == 1
            index, entry = found[0]
            fixture(SERIAL, [s if g is None else g for s, g in zip(saved, entry['skill']['finalGoals'])])
            current = json.loads(prefs(SERIAL)['result'])['runId']
            library(SERIAL)
            tap(SERIAL, 'libraryRun'+str(index))
            tap(SERIAL, 'button1', 'android')
            wait_terminal(lambda: private(SERIAL, PROBE, 'recorded-workflow-result.json'), current)
        fixture(SERIAL, saved)
        library(SERIAL)
        text(SERIAL, 'libraryInput', '执行阅读60')
        snap(SERIAL, out/'ready-for-user.png')
        restored = dict(catalogueUnchanged=prefs(SERIAL)['library'] == state['library'],
            approvalRestored=prefs(SERIAL).get('approved') == state.get('approved'),
            fixtureSavedStateRestored=private(SERIAL, APP, 'workflow-oracle.json')['initial'] == saved,
            userInputPrepared='执行阅读60', activeUSBTarget='tcp:'+str(port))
        write(out/'restored.json', restored)
        assert all(restored[k] for k in ('catalogueUnchanged', 'approvalRestored', 'fixtureSavedStateRestored'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--reaudit', action='store_true')
    parser.add_argument('--selector',choices=['jev','routed'],default='jev')
    args = parser.parse_args()
    reaudit(args.output) if args.reaudit else main(args.output,args.selector)
