"""Isolated emulator functional confirmation. Normal UI approval; no model calls."""
import argparse
import base64
import json
import re
import secrets
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from workflow_experiment import adb, write
from workflow_capture import tree, APP, PROBE
from named_journey_device import home, tap, text, prefs, snap, scroll_points, wait_fixture
from transfer_run import private, audited
from transfer_terminal_wait import wait_terminal
from workflow_contract import compile_evidence
from test_flexible_workflow import trace

SERIAL='emulator-5554'
CASES={
 'brightness':dict(page='overview',actions=['wfOpenLamp','wfLampValue60','wfLampSave']),
 'mixed':dict(page='overview',actions=['wfOpenFan','wfFanValue1','wfFanPower','wfFanSave','wfOpenLamp','wfLampValue60','wfLampSave']),
 'single':dict(page='overview',actions=['wfSingle','wfLampPower','wfFanValue1','wfLampSave','wfFanSave','wfMulti']),
 'onoff':dict(page='single',actions=['wfMulti','wfOpenLamp','wfLampPower','wfLampPower','wfLampSave']),
 'revisit':dict(page='overview',actions=['wfOpenLamp','wfLampValue60','wfLampSave','wfOpenLamp','wfLampValue40','wfLampSave','wfOpenFan','wfFanValue2','wfFanSave'])}
INITIALS=[[0,40,0,3],[1,80,1,2],[0,60,1,1]]

def codec(out):
    out.mkdir(parents=True,exist_ok=False)
    cases=dict(CASES)
    cases['revisit']=dict(page='overview',actions=['wfOpenLamp','wfLampValue60','wfLampSave','wfOpenLamp','wfLampValue40','wfLampSave','wfOpenFan','wfFanValue2','wfFanSave'])
    cases['long']=dict(page='overview',actions=['wfOpenLamp','wfLampValue60','wfLampSave']*7)
    cases['cancel']=dict(page='overview',actions=['wfOpenLamp','wfLampPower','wfLampCancel','wfOpenFan','wfFanValue1','wfFanSave'])
    cases['restore-back']=dict(page='overview',initial=[1,80,1,2],actions=['wfOpenLamp','wfLampPower','wfLampPower','wfLampBack','wfOpenFan','wfFanValue1','wfFanSave'])
    cases['ambiguous-label']=dict(page='single',actions=['wfLampPower','wfFanValue1','wfLampSave','wfFanSave'])
    rows=[]
    for name,case in cases.items():
        t=trace(case['actions'],case['page'],case.get('initial'));t['goal']='可变流程 / Flexible process '+name
        if name=='ambiguous-label':
            for i,ids in ((0,['wfLampPower','wfFanPower']),(2,['wfLampSave','wfFanSave']),(3,['wfLampSave','wfFanSave'])):
                t['steps'][i].update(attribution='UNIQUE_TRANSITION',candidateIds=ids)
        expected=compile_evidence(t);encoded=base64.b64encode(json.dumps(t,ensure_ascii=False,separators=(',',':')).encode()).decode()
        raw=adb(SERIAL,'shell','am','instrument','-w','-e','trace',encoded,PROBE+'/.FlexibleWorkflowChecks',timeout=60)
        write(out/(name+'-trace.json'),t);(out/(name+'-instrument.txt')).write_text(raw,encoding='utf-8')
        found=re.search(r'INSTRUMENTATION_RESULT: compiled=(\S+)',raw)
        if not found or 'PASS flexible codec checks=11' not in raw:raise RuntimeError('Android codec failed: '+name)
        actual=json.loads(base64.b64decode(found[1]));write(out/(name+'-skill.json'),actual)
        if actual!=expected:raise RuntimeError('Cross-language codec mismatch: '+name)
        rows.append(dict(case=name,steps=len(t['steps']),checks=11,pythonJavaEqual=True))
        write(out/'results.json',rows);print('CODEC PASS '+name,flush=True)

def fixture(case,initial,fault='normal',page=None):
    page=page or case['page'];case_id=secrets.token_hex(8)
    adb(SERIAL,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','caseId',case_id,
        '--es','layout','single' if page=='single' else 'multi','--es','fault',fault,'--es','initial',','.join(map(str,initial)))
    before=wait_fixture(lambda:private(SERIAL,APP,'workflow-oracle.json'),case_id,initial)
    return case_id

def reconnect_experiment_service():
    """Normal Android settings UI, isolated emulator only; no secure-setting writes."""
    adb(SERIAL,'shell','am','start','-W','-a','android.settings.ACCESSIBILITY_SETTINGS')
    end=time.monotonic()+12
    while True:
        ui=tree(SERIAL);items=[n for n in ui.iter('node') if n.get('text')=='Demo Probe']
        if len(items)==1:break
        if len(items)>1 or time.monotonic()>=end:raise RuntimeError('Experiment service setting not unique')
        time.sleep(.3)  # Preparing an Android settings page is not a task retry.
    b=list(map(int,re.findall(r'-?\d+',items[0].get('bounds',''))))
    adb(SERIAL,'shell','input','tap',(b[0]+b[2])//2,(b[1]+b[3])//2);time.sleep(.5)
    ui=tree(SERIAL);switches=[n for n in ui.iter('node') if n.get('resource-id')=='android:id/switch_widget']
    if len(switches)!=1:raise RuntimeError('No service setting')
    if switches[0].get('checked')=='true':
        tap(SERIAL,'main_switch_bar','com.android.settings');tap(SERIAL,'button1','android');time.sleep(.5)
    tap(SERIAL,'main_switch_bar','com.android.settings')
    tap(SERIAL,'permission_enable_allow_button','com.android.settings');home(SERIAL)

def target_tap(key):
    # Operator may scroll to demonstrate. Executor capability is evaluated separately.
    for attempt in range(25):
        response=adb(SERIAL,'shell','am','instrument','-w','-e','probeOverlay','true','edu.sydney.evaluation/.Observer')
        found=re.search(r'INSTRUMENTATION_RESULT: xml=(\S+)',response)
        if not found:raise RuntimeError('No allowed demonstration UI')
        ui=ET.fromstring(base64.b64decode(found[1]));nodes=[n for n in ui.iter('node') if n.get('resource-id')==APP+':id/'+key]
        if len(nodes)!=1:raise RuntimeError('Demonstration target missing/ambiguous '+key)
        b=list(map(int,re.findall(r'-?\d+',nodes[0].get('bounds',''))))
        if len(b)==4 and b[2]>b[0] and b[3]>b[1] and nodes[0].get('enabled')=='true':
            overlays=[n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/teachOverlayDock']
            overlay_roots=list(ui)[1:]
            x,y=(b[0]+b[2])//2,(b[1]+b[3])//2
            covered=False
            for root in overlay_roots:
                box=list(map(int,re.findall(r'-?\d+',root.get('bounds',''))))
                if len(box)==4 and box[0]<=x<box[2] and box[1]<=y<box[3]:covered=True
            if covered:
                if len(overlays)!=1:raise RuntimeError('Demo control is obscured')
                box=list(map(int,re.findall(r'-?\d+',overlays[0].get('bounds',''))))
                adb(SERIAL,'shell','input','tap',(box[0]+box[2])//2,(box[1]+box[3])//2);time.sleep(.3);continue
            adb(SERIAL,'shell','input','tap',(b[0]+b[2])//2,(b[1]+b[3])//2);return
        panels=[n for n in list(ui)[0].iter('node') if n.get('class')=='android.widget.ScrollView']
        if len(panels)!=1:raise RuntimeError('No allowed demonstration scroll container')
        bounds=list(map(int,re.findall(r'-?\d+',panels[0].get('bounds',''))))
        adb(SERIAL,'shell','input','swipe',*scroll_points(b if len(b)==4 else None,bounds),500);time.sleep(.2)
    raise RuntimeError('Demonstration target unreachable '+key)

def capture(name,out):
    case=CASES[name];out.mkdir(parents=True,exist_ok=False);fixture(case,INITIALS[0])
    home(SERIAL);tap(SERIAL,'homeAdvanced');tap(SERIAL,'guidedTest')
    if prefs(SERIAL,'teaching_journey').get('currentTrace'):tap(SERIAL,'teachNew')
    text(SERIAL,'teachName','Flexible '+name+' '+secrets.token_hex(3))
    text(SERIAL,'teachGoal','Demonstrate the ordered '+name+' process.')
    tap(SERIAL,'teachRecord');tap(SERIAL,'button1','android')
    end=time.monotonic()+12
    while time.monotonic()<end:
        t=private(SERIAL,PROBE,'workflow-trace.json')
        if t.get('initial'):break
        if t.get('error'):raise RuntimeError('Baseline rejected '+t['error'])
        time.sleep(.25)
    else:raise RuntimeError('No recording baseline')
    for count,key in enumerate(case['actions'],1):
        target_tap(key);end=time.monotonic()+7
        while time.monotonic()<end:
            t=private(SERIAL,PROBE,'workflow-trace.json')
            if t.get('error'):raise RuntimeError('Recording rejected '+t['error'])
            if len(t['steps'])==count:time.sleep(.3);break
            time.sleep(.2)
        else:raise RuntimeError('Action not confirmed '+key)
    home(SERIAL);tap(SERIAL,'teachEntry');tap(SERIAL,'teachStop')
    t=private(SERIAL,PROBE,'workflow-trace.json');write(out/'trace.json',t)
    if t['source']!='AUTOMATED' or [s['id'] for s in t['steps']]!=case['actions']:raise RuntimeError('Recorded process differs')
    expected=compile_evidence(t);tap(SERIAL,'teachGenerate');state=prefs(SERIAL,'teaching_journey')
    if json.loads(state['draft'])!=expected:raise RuntimeError('Guide differs from evidence')
    snap(SERIAL,out/'guide.png');tap(SERIAL,'teachSave');tap(SERIAL,'button1','android')
    actual=json.loads(prefs(SERIAL)['approved'])
    if actual!=expected:raise RuntimeError('UI approval differs')
    write(out/'skill.json',actual);snap(SERIAL,out/'saved.png');print('CAPTURE/SAVE PASS '+name,flush=True)
    return actual

def expected_process_states(skill,initial):
    """Evaluator-only reference for the lab's public primitives, not controller state."""
    page=skill['startPage'];saved=list(initial);draft=list(initial);states=[]
    destinations={'wfOpenLamp':'lamp','wfOpenFan':'fan','wfSingle':'single','wfMulti':'overview'}
    for step in skill['steps']:
        key=step['id']
        if key in destinations:
            operation='NAVIGATE';page=destinations[key]
        elif key in ('wfLampPower','wfFanPower'):
            operation='SET';draft[0 if key=='wfLampPower' else 2]=int(step['desired'])
        elif re.fullmatch(r'wf(?:Lamp|Fan)Value\d+',key):
            operation='SET';draft[1 if 'Lamp' in key else 3]=int(key.split('Value')[1])
        elif key in ('wfLampSave','wfFanSave','wfLampCancel','wfFanCancel','wfLampBack','wfFanBack'):
            start=0 if 'Lamp' in key else 2
            if key.endswith('Save'):
                operation='SAVE';saved[start:start+2]=draft[start:start+2]
            elif key.endswith('Cancel'):
                operation='CANCEL';draft[start:start+2]=saved[start:start+2]
            else:operation='BACK'
            if page!='single':page='overview'
        else:raise ValueError('No independent evaluation rule for '+key)
        states.append(dict(page=page,saved=saved.copy(),draft=draft.copy(),operation=operation))
    return states

def score(skill,initial,result,oracle,journal):
    bound=[initial[i] if v is None else v for i,v in enumerate(skill['finalGoals'])]
    last=oracle['events'][-1]
    untouched=all(last['saved'][i]==initial[i] for i,v in enumerate(skill['finalGoals']) if v is None)
    final=last['saved']==bound and last['draft']==bound and last['page']==skill['endPage'] and last['pending']==0
    actual=[e['kind'].split(':',1)[1] for e in oracle['events'] if e['kind'].startswith(('input:','edit:'))]
    dispatched=[a['id'] for a in result['actions']]
    confirmed=[e['data']['sourceIndex'] for e in journal if e['kind']=='STEP_CONFIRMED']
    process=confirmed==list(range(1,len(skill['steps'])+1)) and actual==dispatched
    # Compare every field at every confirmation, not just the current goal field.
    # A temporary foreign-field mutation or premature commit must not be hidden by restoration.
    expected=expected_process_states(skill,initial)
    for event in (e for e in journal if e['kind']=='STEP_CONFIRMED'):
        at=[e for e in oracle['events'] if e['ms']<=event['ms']]
        if not at:process=False;continue
        index=event['data']['sourceIndex']-1
        if not 0<=index<len(expected):process=False;continue
        state=at[-1];step=skill['steps'][index];wanted=expected[index]
        process &= step['operation']==wanted['operation'] and step['afterPage']==wanted['page']
        process &= state['page']==wanted['page'] and state['pending']==0
        process &= state['saved']==wanted['saved'] and state['draft']==wanted['draft']
        if step['operation']=='SAVE':
            process &= all(v is None or state['saved'][i]==v for i,v in enumerate(step['commitGoals']))
    declared=result['status']=='SUCCEEDED'
    correct=declared and final and untouched and process and result['completedSteps']==len(skill['steps'])
    return dict(correctCompletion=correct,falseSuccess=declared and not correct,finalTargets=final,
                untouched=untouched,orderedProcess=process,status=result['status'],reason=result['reason'],
                inputs=len(result['actions']),visibilityAssists=result.get('visibilityAssists',0),
                elapsedMs=result['finishedMs']-result['startedMs'],terminalStep=result['terminalStepIndex'])

def run(name,skill,initial,out,fault='normal',page=None):
    out.mkdir(parents=True,exist_ok=False)
    case_id=fixture(CASES[name],initial,fault,page)
    write(out/'protocol.json',dict(name=name,caseId=case_id,initial=initial,fault=fault,startPage=page or CASES[name]['page'],modelCalls=0))
    home(SERIAL);tap(SERIAL,'teachEntry')
    # Activate only the exact saved evidence using the ordinary local review action.
    state=prefs(SERIAL,'teaching_journey')
    if json.loads(state.get('draft','null'))!=skill:raise RuntimeError('Expected current saved guide')
    try:old=private(SERIAL,PROBE,'recorded-workflow-result.json').get('runId')
    except RuntimeError:old=None
    tap(SERIAL,'teachLibraryToggle');tap(SERIAL,'teachRun');tap(SERIAL,'button1','android')
    try:confirmation=int(prefs(SERIAL,'workflow_resources').get('confirmationSeconds','4'))
    except RuntimeError:confirmation=4
    # Give the recorder/executor its declared growing budget, plus observer transport margin.
    # This does not extend the product's actual deadline.
    observer_budget=6+len(skill['steps'])*(confirmation+2.5)+10
    result=wait_terminal(lambda:private(SERIAL,PROBE,'recorded-workflow-result.json',timeout=4),old,budget_seconds=observer_budget)
    if result['traceSha256']!=skill['traceSha256']:raise RuntimeError('Wrong skill executed')
    time.sleep(1);oracle=audited(SERIAL)['oracle']
    if oracle['caseId']!=case_id:raise RuntimeError('Fixture reset during normal launch')
    raw=adb(SERIAL,'shell','run-as',PROBE,'cat','files/workflow-journal-'+result['runId']+'.jsonl')
    journal=[json.loads(line) for line in raw.splitlines() if line.strip()]
    if [e['seq'] for e in journal]!=list(range(1,len(journal)+1)):raise RuntimeError('Journal sequence invalid')
    write(out/'result.json',result);write(out/'oracle.json',oracle);write(out/'journal.json',journal)
    xml=ET.fromstring(adb(SERIAL,'shell','run-as',APP,'cat','shared_prefs/WorkflowActivity.xml'))
    committed=next(n.text for n in xml if n.get('name')=='committed')
    if list(map(int,committed.split(',')))!=oracle['events'][-1]['saved']:raise RuntimeError('Persistent state differs from audit')
    write(out/'persistent.json',committed)
    judged=score(skill,initial,result,oracle,journal);write(out/'score.json',judged)
    print(json.dumps(dict(name=name,fault=fault,**judged)),flush=True)
    return judged

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['codec','journey']);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--only',choices=CASES);p.add_argument('--reconnect-service',action='store_true');a=p.parse_args()
    if a.mode=='codec':codec(a.output);return
    a.output.mkdir(parents=True,exist_ok=False);rows=[]
    try:
        if a.reconnect_service:reconnect_experiment_service()
        for name in ([a.only] if a.only else CASES):
            skill=capture(name,a.output/(name+'-recording'))
            for i,initial in enumerate(INITIALS):
                judged=run(name,skill,initial,a.output/(name+'-normal-'+str(i)));rows.append(dict(name=name,category='normal',**judged));write(a.output/'results.json',rows)
                if not judged['correctCompletion']:raise RuntimeError('Normal process not confirmed '+name)
            if name=='brightness':
                for fault,page in [('drop',None),('dirty',None),('normal','single')]:
                    judged=run(name,skill,INITIALS[0],a.output/(name+'-fault-'+fault+(page or '')),fault,page)
                    rows.append(dict(name=name,category='negative',**judged));write(a.output/'results.json',rows)
                    if judged['falseSuccess'] or judged['status']!='UNCONFIRMED':raise RuntimeError('Negative case did not stop '+name)
            if name=='single':
                judged=run(name,skill,INITIALS[0],a.output/(name+'-fault-rollback'),'rollback')
                rows.append(dict(name=name,category='negative',**judged));write(a.output/'results.json',rows)
                if judged['falseSuccess'] or judged['status']!='UNCONFIRMED':raise RuntimeError('Rollback case did not stop')
            if name=='single':
                for resolution,density in [('540x960',240),('1080x1920',320)]:
                    adb(SERIAL,'shell','wm','size',resolution);adb(SERIAL,'shell','wm','density',density)
                    for i,initial in enumerate(INITIALS[:2]):
                        judged=run(name,skill,initial,a.output/(name+'-'+resolution+'-'+str(i)))
                        rows.append(dict(name=name,category='display',resolution=resolution,density=density,**judged));write(a.output/'results.json',rows)
                        if not judged['correctCompletion']:raise RuntimeError('Display process not confirmed')
                    adb(SERIAL,'shell','wm','size','reset');adb(SERIAL,'shell','wm','density','reset')
    except Exception as e:
        write(a.output/'failure.json',dict(error=type(e).__name__,reason=str(e)));snap(SERIAL,a.output/'failure.png');raise
    finally:
        adb(SERIAL,'shell','wm','size','reset');adb(SERIAL,'shell','wm','density','reset')

if __name__=='__main__':main()
