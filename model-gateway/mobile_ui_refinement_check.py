"""UI-only matrix and execution regression. No model calls or private approval writes."""
import argparse
import hashlib
import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

from named_journey_device import home, library, tap, text, snap, prefs, fixture, node, PROBE, APP
from workflow_capture import tree
from workflow_experiment import adb, write
from transfer_run import private
from ui_polish_check import layout, validate_layout, find, inventory
from migration_matrix import display
from user_robustness import restore_display, effective_display_value

CONFIGS = [('native', None, None), ('compact', '720x1560', '360'), ('wide', '1200x1920', '320')]


def display_matrix(serial, out):
    out.mkdir(parents=True, exist_ok=False)
    original = display(serial)
    old = private(serial, APP, 'workflow-oracle.json')
    saved = old['events'][-1]['saved'] if old.get('events') else old['initial']
    before = inventory(serial)
    home(serial)
    original_en = find(tree(serial), 'homeLanguage').get('text') == '中文'
    rows = []
    write(out/'protocol.json', dict(configs=CONFIGS, device=serial, modelCalls=0,
        scope='One physical phone with reversible display overrides, not multiple devices', originalDisplay=original))
    try:
        for name, size, dpi in CONFIGS:
            if size:
                adb(serial, 'shell', 'wm', 'size', size)
                adb(serial, 'shell', 'wm', 'density', dpi)
                time.sleep(1)
            root = out/name
            layout(serial, root)
            current = display(serial)
            density = int(effective_display_value(current['density']))/160
            fixture(serial, saved)
            pages = [('overview', None), ('lamp', 'wfOpenLamp'), ('fan', 'wfOpenFan')]
            for page, control in pages:
                if control:
                    tap(serial, control, APP)
                ui = tree(serial)
                snap(serial, root/('fixture-'+page+'.png'))
                measures = validate_layout(ui, density)
                if page != 'overview':
                    prefix = 'wfLamp' if page == 'lamp' else 'wfFan'
                    selected = saved[1 if page == 'lamp' else 3]
                    options = [n for n in ui.iter('node') if n.get('class') == 'android.widget.RadioButton']
                    assert len(options) == (5 if page == 'lamp' else 3)
                    checked = [n.get('resource-id') for n in options if n.get('checked') == 'true']
                    assert checked == [APP+':id/'+prefix+'Value'+str(selected)]
                    tap(serial, prefix+'Back', APP)
                rows.append(dict(config=name, page=page, controls=measures, semanticStatePreserved=True))
                write(out/'fixture-checks.json', rows)
            assert private(serial, APP, 'workflow-oracle.json')['events'][-1]['saved'] == saved
            assert inventory(serial) == before
            print('PASS display and bilingual pages: '+name, flush=True)
    finally:
        restore_display(serial, original)
        fixture(serial, saved)
        home(serial)
        if (find(tree(serial), 'homeLanguage').get('text') == '中文') != original_en:
            tap(serial, 'homeLanguage')
        write(out/'restoration.json', dict(displayRestored=display(serial)==original,
            catalogueAndCoreUnchanged=inventory(serial)==before,
            fixtureRestored=private(serial,APP,'workflow-oracle.json')['initial']==saved))


def text_checks(serial, out):
    out.mkdir(parents=True, exist_ok=False)
    before = inventory(serial)
    state = prefs(serial)
    library(serial)
    old_text = find(tree(serial), 'libraryInput').get('text', '')
    old_en = find(tree(serial), 'libraryLanguage').get('text') == '中文'
    rows = []
    write(out/'protocol.json', dict(modelCalls=0, languages=['Chinese', 'English'], inputLength=500,
        checks=['long input preserved', 'keyboard visible and primary reachable', 'preview/cancel without execution']))
    try:
        for en in (False, True):
            library(serial)
            if (find(tree(serial), 'libraryLanguage').get('text') == '中文') != en:
                tap(serial, 'libraryLanguage')
            value = (('Read and review this saved workflow. ' if en else '这是界面长文本检查，不执行任何操作。')*40)[:500]
            text(serial, 'libraryInput', value)
            assert find(tree(serial), 'libraryInput').get('text') == value
            tap(serial, 'libraryInput')
            # The evaluator sets text through UI; tapping additionally tests the real IME.
            shown = adb(serial, 'shell', 'dumpsys', 'input_method')
            assert 'mInputShown=true' in shown or 'isInputViewShown=true' in shown
            node(serial, 'libraryChoose')
            snap(serial, out/('keyboard-'+('en' if en else 'zh')+'.png'))
            tap(serial, 'libraryLanguage')
            assert find(tree(serial), 'libraryInput').get('text') == value
            tap(serial, 'libraryLanguage')
            # No selection request is sent for these artificial commands.
            adb(serial, 'shell', 'input', 'keyevent', '4')
            assert prefs(serial).get('approved') == state.get('approved')
            assert prefs(serial).get('result') == state.get('result')
            rows.append(dict(english=en, length=len(value), keyboardShown=True, primaryReachable=True,inputPreserved=True, modelCalls=0))
            write(out/'checks.json', rows)
            print('PASS long input and keyboard: '+('en' if en else 'zh'), flush=True)
    finally:
        library(serial)
        text(serial, 'libraryInput', old_text or ' ')
        if (find(tree(serial), 'libraryLanguage').get('text') == '中文') != old_en:
            tap(serial, 'libraryLanguage')
        home(serial)
        write(out/'restoration.json', dict(catalogueAndCoreUnchanged=inventory(serial)==before,
            approvalUnchanged=prefs(serial).get('approved')==state.get('approved')))


def execution_checks(serial, out):
    from ui_polish_check import regress
    from named_journey_execution import run as whole_run
    from jev_deployment_smoke import verify_execution
    regress(serial, out)
    rows = json.loads((out/'results.json').read_text(encoding='utf-8'))
    for row in rows:
        verify_execution(row, partial=True)
    state = prefs(serial)
    before = inventory(serial)
    old = private(serial, APP, 'workflow-oracle.json')
    saved = old['events'][-1]['saved'] if old.get('events') else old['initial']
    whole = []
    try:
        for name, case in [('reading', dict(skill='reading',condition='none',initial=[0,40,0,3])),
                           ('bright', dict(skill='bright',condition='none',initial=[0,40,0,1]))]:
            row = whole_run(serial, case, out/('whole-'+name))
            verify_execution(row, partial=False)
            whole.append(row)
            write(out/'whole-results.json', whole)
            print('PASS full workflow: '+name, flush=True)
    finally:
        # Select previous approval through the existing preview/confirm UI.
        if prefs(serial).get('approved') != state.get('approved'):
            from transfer_terminal_wait import wait_terminal
            matches = [(i,e) for i,e in enumerate(json.loads(state['library']))
                       if e['skill'] == json.loads(state['approved'])]
            assert len(matches) == 1
            i, entry = matches[0]
            fixture(serial, [s if g is None else g for s,g in zip(saved,entry['skill']['finalGoals'])])
            previous = json.loads(prefs(serial)['result'])['runId']
            library(serial);tap(serial, 'libraryRun'+str(i));tap(serial, 'button1', 'android')
            result = wait_terminal(lambda:private(serial,PROBE,'recorded-workflow-result.json'),previous)
            write(out/'whole-restored-selection.json',dict(status=result['status'],reason=result['reason']))
        fixture(serial, saved);home(serial)
        assert inventory(serial) == before
    write(out/'strict-summary.json',dict(partialPassed=len(rows),wholePassed=len(whole),modelCalls=0,
        falseSuccess=0,nonTargetViolation=0,extraInputs=0,postTerminalInputs=0,
        scope='UI regression with existing reviewed packages, not new generalization or model benchmark'))


def model_preview_checks(serial, out):
    """Two real selection requests; cancel the preview, never run a skill."""
    out.mkdir(parents=True, exist_ok=False)
    before = inventory(serial)
    state = prefs(serial)
    oracle = private(serial, APP, 'workflow-oracle.json')
    library(serial)
    original_input = find(tree(serial), 'libraryInput').get('text','')
    original_en = find(tree(serial), 'libraryLanguage').get('text') == '中文'
    entry = [e for e in json.loads(before['library']) if e['skill']['finalGoals']==[1,60,1,1]]
    assert len(entry) == 1
    rows = []
    write(out/'protocol.json',dict(commands=['执行阅读60','Run Reading60.'], realRequests=2,
        executionAllowed=False, purpose='Installed UI and bridge smoke, not a model accuracy benchmark'))
    try:
        for en, command in [(False,'执行阅读60'),(True,'Run Reading60.')]:
            library(serial)
            if (find(tree(serial),'libraryLanguage').get('text')=='中文') != en:
                tap(serial,'libraryLanguage')
            text(serial,'libraryInput',command)
            start = time.monotonic()
            tap(serial,'libraryChoose')
            end = time.monotonic()+55
            while time.monotonic()<end:
                ui = tree(serial)
                if any(n.get('resource-id')=='android:id/button1' for n in ui.iter('node')):
                    break
                time.sleep(.4)
            else:
                snap(serial,out/('failed-'+('en' if en else 'zh')+'.png'))
                raise RuntimeError('No model-backed preview; unavailable is not a successful selection')
            assert any(entry[0]['name'] in n.get('text','') for n in ui.iter('node'))
            elapsed = round((time.monotonic()-start)*1000)
            snap(serial,out/('preview-'+('en' if en else 'zh')+'.png'))
            tap(serial,'button2','android')
            assert prefs(serial).get('result')==state.get('result')
            assert prefs(serial).get('approved')==state.get('approved')
            assert private(serial,APP,'workflow-oracle.json')==oracle
            rows.append(dict(english=en,command=command,selected=entry[0]['name'],cancelled=True,
                noExecution=True,automationToPreviewMs=elapsed))
            write(out/'checks.json',rows)
            print('PASS real model preview/cancel: '+('en' if en else 'zh'),flush=True)
    finally:
        library(serial);text(serial,'libraryInput',original_input or ' ')
        if (find(tree(serial),'libraryLanguage').get('text')=='中文') != original_en:
            tap(serial,'libraryLanguage')
        home(serial)
        write(out/'restoration.json',dict(catalogueAndCoreUnchanged=inventory(serial)==before,
            approvalUnchanged=prefs(serial).get('approved')==state.get('approved'),
            resultUnchanged=prefs(serial).get('result')==state.get('result')))


def deployment_audit(serial, out):
    """Match installed APK bytes to final artifacts and compare the original catalogue."""
    out.mkdir(parents=True, exist_ok=False)
    root = Path(__file__).resolve().parents[1]
    baseline = json.loads((root/'evaluation/mobile-ui-v2/before/inventory.json').read_text(encoding='utf-8'))
    current = inventory(serial)
    assert current == baseline
    artifacts = [(PROBE,'android-agent-probe/build/manual/demo-probe-ui-v2.apk',26),
                 (APP,'android-transfer-bench/build/manual/transfer-bench-ui-v2.apk',6)]
    rows = []
    for package, file, version in artifacts:
        raw = adb(serial,'shell','pm','path',package).strip()
        assert raw.startswith('package:/data/app/') and '\n' not in raw
        installed_hash = adb(serial,'shell','sha256sum',raw[len('package:'):]).split()[0]
        artifact_hash = hashlib.sha256((root/file).read_bytes()).hexdigest()
        assert installed_hash == artifact_hash
        description = adb(serial,'shell','dumpsys','package',package)
        assert 'versionCode='+str(version)+' ' in description
        rows.append(dict(package=package,versionCode=version,artifact=file,sha256=artifact_hash,installedBytesMatch=True))
    home(serial)
    before_home = ET.parse(root/'evaluation/mobile-ui-v2/before/home.xml').getroot()
    original_en = find(before_home,'homeLanguage').get('text')=='中文'
    if (find(tree(serial),'homeLanguage').get('text')=='中文') != original_en:
        tap(serial,'homeLanguage')
    snap(serial,out/'home.png')
    node(serial,'homeService')
    service = find(tree(serial),'homeService').get('text','')
    assert '已连接' in service or 'connected' in service.lower() and 'disconnected' not in service.lower()
    write(out/'deployment.json',dict(packages=rows,catalogueExactUnchanged=True,
        skills=len(json.loads(current['library'])),sevenCoreSourcesUnchanged=True,
        originalLocaleRestored=True,serviceConnected=True,display=display(serial)))
    print('PASS installed APK bytes, five preserved skills, protected sources and original locale',flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['display','text','execution','model','audit'])
    parser.add_argument('--device', default='R5CW134LLBZ')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    {'display':display_matrix,'text':text_checks,'execution':execution_checks,'model':model_preview_checks,'audit':deployment_audit}[args.mode](args.device,args.output)
