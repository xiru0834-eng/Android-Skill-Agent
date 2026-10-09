"""Scoped visual checks of Demo Probe. Does not call models or approve skills."""
import argparse
import hashlib
import json
import time
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from named_journey_device import home, tap, snap, prefs, text, node, PROBE
from workflow_capture import tree
from workflow_experiment import adb

SOURCE=Path(__file__).resolve().parents[1]/'android-agent-probe/app/src/main/java/edu/sydney/probe'
PROTECTED=['WorkflowRunner.java','WorkflowRecorder.java','WorkflowStore.java','WorkflowCodec.java','WorkflowSelectionClient.java','TeachingClient.java','TeachingGuard.java']

def inventory(serial):
    data=prefs(serial)
    # Read only the reviewed catalogue; pairing secrets are deliberately excluded.
    return dict(library=data.get('library','[]'),core={name:hashlib.sha256((SOURCE/name).read_bytes()).hexdigest() for name in PROTECTED})

def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def capture(serial,out):
    out.mkdir(parents=True,exist_ok=False)
    write(out/'inventory.json',inventory(serial))
    home(serial);snap(serial,out/'home.png')
    tap(serial,'namedLibrary');snap(serial,out/'skills.png')
    home(serial);tap(serial,'teachEntry');snap(serial,out/'teach.png')
    home(serial)
    print('Captured three scoped pages; no model calls, recording or execution.')

def find(ui,key):
    matches=[n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/'+key]
    if len(matches)!=1:raise AssertionError('Expected unique control: '+key)
    return matches[0]

def visible(ui,key):
    return any(n.get('resource-id')==PROBE+':id/'+key for n in ui.iter('node'))

def validate_layout(ui,density):
    """Measure visible buttons, switches and radio options; exclude viewport clipping."""
    panels=[n for n in ui.iter('node') if n.get('class')=='android.widget.ScrollView']
    assert len(panels)==1
    area=list(map(int,re.findall(r'-?\d+',panels[0].get('bounds',''))))
    measured=[]
    for n in ui.iter('node'):
        if n.get('class') not in ('android.widget.Button','android.widget.RadioButton','android.widget.Switch'):continue
        b=list(map(int,re.findall(r'-?\d+',n.get('bounds',''))))
        if len(b)!=4 or b[2]<=b[0] or b[3]<=b[1]:continue
        assert b[0]>=area[0] and b[2]<=area[2], 'Horizontal clipping: '+n.get('resource-id','')
        # Accessibility bounds are clipped to the viewport. A node ending
        # exactly at its edge may represent only the top of a larger button.
        pinned=b[1]>=0 and b[3]<area[1]
        if not pinned and (b[1]<=area[1] or b[3]>=area[3]):continue
        height=(b[3]-b[1])/density
        assert height>=47.5,'Small tap target: '+n.get('resource-id','')
        width=(b[2]-b[0])/density
        assert width>=47.5,'Narrow tap target: '+n.get('resource-id','')
        measured.append(dict(id=n.get('resource-id',''),heightDp=round(height,1),widthDp=round(width,1)))
    assert measured
    return measured

def check(serial,out):
    out.mkdir(parents=True,exist_ok=False)
    before=inventory(serial);state=prefs(serial);teaching=prefs(serial,'teaching_journey')
    rows=[];original_input=None;original_english=None
    def passed(name,**details):
        rows.append(dict(check=name,status='PASS',**details));write(out/'checks.json',rows)
        print('PASS '+name,flush=True)
    try:
        home(serial);ui=tree(serial);original_english=find(ui,'homeLanguage').get('text')=='中文'
        density_text=adb(serial,'shell','wm','density');density=int(re.findall(r'\d+',density_text)[-1])/160
        snap(serial,out/'home.png');passed('home_layout',buttons=validate_layout(ui,density))
        assert not visible(ui,'guidedTest');tap(serial,'homeAdvanced');node(serial,'guidedTest');tap(serial,'homeAdvanced')
        passed('legacy_tools_fold_and_reach')
        home(serial);tap(serial,'namedLibrary');ui=tree(serial)
        original_input=find(ui,'libraryInput').get('text','')
        snap(serial,out/'skills.png');passed('library_layout',buttons=validate_layout(ui,density))
        assert not visible(ui,'libraryImport');tap(serial,'libraryTools');node(serial,'libraryImport');node(serial,'libraryReview');node(serial,'libraryConnection')
        snap(serial,out/'management.png');tap(serial,'libraryTools');passed('library_management_fold_and_reach')
        text(serial,'libraryInput','Interface check / 界面检查');tap(serial,'libraryLanguage')
        assert find(tree(serial),'libraryInput').get('text')=='Interface check / 界面检查'
        snap(serial,out/'skills-other-language.png');tap(serial,'libraryLanguage')
        assert find(tree(serial),'libraryInput').get('text')=='Interface check / 界面检查'
        passed('library_language_preserves_input')
        # Android shell drops a zero-length instrumentation argument. Whitespace
        # exercises the same trimmed-empty branch through normal UI input.
        text(serial,'libraryInput',' ');tap(serial,'libraryChoose');ui=tree(serial)
        message=find(ui,'libraryStatus').get('text','')
        assert ('先输入' in message or 'Enter an instruction' in message) and 'EMPTY_TEXT' not in message
        snap(serial,out/'empty-command.png');passed('empty_command_readable_no_request')
        text(serial,'libraryInput',original_input)
        tap(serial,'libraryRun0');ui=tree(serial)
        assert any(n.get('resource-id')=='android:id/button1' for n in ui.iter('node'))
        snap(serial,out/'preview.png');tap(serial,'button2','android')
        current=prefs(serial);assert current.get('approved')==state.get('approved') and current.get('result')==state.get('result')
        passed('preview_cancel_no_execution_or_approval')
        home(serial);tap(serial,'teachEntry');ui=tree(serial)
        original_name=find(ui,'teachName').get('text','');original_goal=find(ui,'teachGoal').get('text','')
        snap(serial,out/'teach.png');passed('teaching_layout',buttons=validate_layout(ui,density))
        tap(serial,'teachLanguage');ui=tree(serial)
        assert find(ui,'teachName').get('text','')==original_name and find(ui,'teachGoal').get('text','')==original_goal
        snap(serial,out/'teach-other-language.png');tap(serial,'teachLanguage');passed('teaching_language_preserves_inputs')
        assert not visible(tree(serial),'teachSetup');tap(serial,'teachTools');node(serial,'teachSetup');node(serial,'teachDetails');tap(serial,'teachTools')
        passed('teaching_tools_fold_and_reach')
        tap(serial,'teachRecord');ui=tree(serial)
        assert any(n.get('resource-id')=='android:id/button1' for n in ui.iter('node'))
        snap(serial,out/'record-start-confirmation.png');tap(serial,'button2','android')
        current=prefs(serial,'teaching_journey');assert current.get('currentTrace')==teaching.get('currentTrace')
        assert inventory(serial)==before
        passed('record_confirmation_cancel_keeps_skill_and_trace')
        home(serial);ui=tree(serial)
        assert (find(ui,'homeLanguage').get('text')=='中文')==original_english
        assert '已连接' in find(ui,'homeService').get('text','') or 'connected' in find(ui,'homeService').get('text','').lower() and 'disconnected' not in find(ui,'homeService').get('text','').lower()
        passed('service_connected_and_shared_locale_restored')
        write(out/'inventory-after.json',inventory(serial));passed('catalogue_and_seven_core_sources_unchanged',skills=len(json.loads(before['library'])))
    except Exception as e:
        write(out/'failure.json',dict(error=type(e).__name__,reason=str(e)));raise
    finally:
        if original_input is not None:
            home(serial);tap(serial,'namedLibrary');text(serial,'libraryInput',original_input or ' ')
        home(serial)
        ui=tree(serial)
        if original_english is not None and (find(ui,'homeLanguage').get('text')=='中文')!=original_english:tap(serial,'homeLanguage')

def layout(serial,out):
    out.mkdir(parents=True,exist_ok=False)
    density=int(re.findall(r'\d+',adb(serial,'shell','wm','density'))[-1])/160
    rows=[];home(serial)
    original_english=find(tree(serial),'homeLanguage').get('text')=='中文'
    for en in (False,True):
        home(serial)
        if (find(tree(serial),'homeLanguage').get('text')=='中文')!=en:tap(serial,'homeLanguage')
        for page,key in [('home',None),('skills','namedLibrary'),('teach','teachEntry')]:
            home(serial)
            if key:tap(serial,key)
            ui=tree(serial);filename=page+('-en' if en else '-zh')+'.png';snap(serial,out/filename)
            rows.append(dict(page=page,english=en,buttons=validate_layout(ui,density)))
            action={'home':'namedLibrary','skills':'libraryChoose','teach':'teachRecord'}[page]
            node(serial,action);snap(serial,out/('reachable-'+filename))
            rows.append(dict(page=page,english=en,primaryReachable=True,buttons=validate_layout(tree(serial),density)))
    home(serial)
    if (find(tree(serial),'homeLanguage').get('text')=='中文')!=original_english:tap(serial,'homeLanguage')
    write(out/'layout-checks.json',rows);print('PASS six bilingual page layouts',flush=True)

def regress(serial,out):
    from partial_journey import cases,run
    from transfer_run import private
    from named_journey_device import APP,fixture
    out.mkdir(parents=True,exist_ok=False)
    original=prefs(serial);old=private(serial,APP,'workflow-oracle.json')
    saved=old['events'][-1]['saved'] if old.get('events') else old['initial']
    before=inventory(serial);rows=[]
    write(out/'protocol.json',dict(cases=cases(),budgetMs=30000,postAuditSeconds=5,modelCalls=0,purpose='UI execution regression, not a new model benchmark'))
    try:
        for i,case in enumerate(cases()):
            row=run(serial,case,out/f'run-{i:02d}');rows.append(row);write(out/'results.json',rows)
            print(json.dumps(dict(index=i,skill=case['skill'],condition=case['condition'],actual=row['actual_success'],status=row['status'],nonTargetViolation=row['non_target_violation'],unexpected=row['unexpectedInputs'],extra=row['extraInputs'],ms=row['elapsed_ms'])),flush=True)
        assert inventory(serial)==before
    finally:
        # Restore the formerly selected skill through its real confirmation UI,
        # then restore only the controlled fixture's starting state.
        approved=original.get('approved');items=json.loads(before['library'])
        match=[i for i,e in enumerate(items) if json.loads(approved or '{}')==e['skill']]
        if len(match)==1 and prefs(serial).get('approved')!=approved:
            from named_journey_device import library
            from transfer_terminal_wait import wait_terminal
            fixture(serial,saved);p=prefs(serial).get('result');old_run=json.loads(p)['runId'] if p and p.startswith('{') else None
            library(serial);tap(serial,'libraryRun'+str(match[0]));tap(serial,'button1','android')
            restored=wait_terminal(lambda:private(serial,PROBE,'recorded-workflow-result.json',timeout=3),old_run)
            write(out/'restored-selected-skill.json',dict(status=restored['status'],reason=restored['reason']))
        fixture(serial,saved);home(serial)
        write(out/'restoration.json',dict(catalogueUnchanged=inventory(serial)==before,previousSelectionRestored=prefs(serial).get('approved')==approved,fixtureRestored=private(serial,APP,'workflow-oracle.json')['initial']==saved))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--device',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--mode',choices=['capture','check','layout','regress'],default='capture')
    a=p.parse_args();globals()[a.mode](a.device,a.output)
