"""Isolated AVD, ordinary teaching/review/run UI; no private approval writes."""
import argparse
import hashlib
import json
import random
import re
import shutil
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import flexible_device_checks as native
from workflow_experiment import adb,write,ROOT
from workflow_capture import tree as raw_tree,PROBE,APP
from named_journey_device import home,tap,text,prefs,snap,library,wait_fixture
from transfer_run import private,audited
from transfer_terminal_wait import wait_terminal
from task2_device_checks import await_approved
from entry_preflight import application_service_state
from task3_protocol import FLOWS,INITIALS,cases,summary,judge
from workflow_contract import compile_evidence

SERIAL='emulator-5554'
PREPARATION_READS=[]


def preparation_tree(serial,clock=time.monotonic,sleep=time.sleep):
    """Only bounded observation retries; never a click or business recovery."""
    until=clock()+6;attempts=0
    while clock()<until:
        attempts+=1
        try:return raw_tree(serial)
        except RuntimeError as error:
            if str(error)!='No allowed UI evidence':raise
            PREPARATION_READS.append(dict(reason=str(error),attempt=attempts,operatorMs=round(clock()*1000)))
            sleep(.2)
    raise RuntimeError('PREPARATION_OBSERVATION_TIMEOUT')


tree=preparation_tree


def prepare_teaching(language='en'):
    home(SERIAL)
    if not application_service_state(tree(SERIAL)):raise RuntimeError('APPLICATION_SERVICE_NOT_READY')
    tap(SERIAL,'homeAdvanced');tap(SERIAL,'guidedTest')
    if prefs(SERIAL,'teaching_journey').get('currentTrace'):management_control('teachNew')
    ui=tree(SERIAL);switch=next(n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/teachLanguage')
    current='zh' if switch.get('text')=='English' else 'en'
    if current!=language:tap(SERIAL,'teachLanguage')


def optional_prefs(name='recorded_workflows'):
    try:return prefs(SERIAL,name)
    except RuntimeError as error:
        if 'No such file' not in str(error):raise
        return {}


def management_control(key,clock=time.monotonic,sleep=time.sleep):
    """One normal management click; no input while a window is transitioning."""
    ready_until=clock()+6
    for attempt in range(20):
        while True:
            if clock()>=ready_until:raise RuntimeError('MANAGEMENT_TRANSITION_TIMEOUT')
            ui=tree(SERIAL)
            panels=[n for n in ui.iter('node') if n.get('class')=='android.widget.ScrollView']
            if len(panels)>1:raise RuntimeError('MANAGEMENT_SCROLL_AMBIGUOUS')
            if panels:break
            sleep(.2)
        found=[n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/'+key]
        if len(found)>1:raise RuntimeError('MANAGEMENT_CONTROL_AMBIGUOUS')
        panel=list(map(int,re.findall(r'-?\d+',panels[0].get('bounds',''))))
        if len(panel)!=4 or panel[3]<=panel[1]:raise RuntimeError('MANAGEMENT_SCROLL_NOT_READY')
        target=list(map(int,re.findall(r'-?\d+',found[0].get('bounds','')))) if found else None
        if target and len(target)==4 and panel[0]<=target[0]<target[2]<=panel[2] and panel[1]<=target[1]<target[3]<=panel[3] and found[0].get('enabled')=='true' and found[0].get('clickable')=='true':
            adb(SERIAL,'shell','input','tap',(target[0]+target[2])//2,(target[1]+target[3])//2)
            sleep(.7);return
        x=(panel[0]+panel[2])//2;high=int(panel[1]+.35*(panel[3]-panel[1]));low=int(panel[1]+.70*(panel[3]-panel[1]))
        # Android can clip the top to the viewport while leaving a negative
        # bottom for offscreen nodes. Never click that rectangle; scroll up.
        above=bool(target and len(target)==4 and (target[1]<panel[1] or target[3]<=panel[1]))
        adb(SERIAL,'shell','input','swipe',x,high if above else low,x,low if above else high,650)
        sleep(.3);ready_until=clock()+6
    raise RuntimeError('MANAGEMENT_CONTROL_UNREACHABLE')


def source_hashes():
    files=[ROOT/'model-gateway'/name for name in ['task3_protocol.py','task3_device_checks.py','task3_batch.py','flexible_device_checks.py','named_journey_device.py','task2_device_checks.py','task2_file_checks.py','workflow_contract.py','flexible_workflow.py','transfer_run.py','transfer_terminal_wait.py']]
    files+=list((ROOT/'android-agent-probe/app/src/main').rglob('*.java'))
    files+=list((ROOT/'android-transfer-bench/app/src/main').rglob('*.java'))
    files+=list((ROOT/'evaluation/android-observer/app/src/main').rglob('*.java'))
    files+=[ROOT/p for p in ['android-agent-probe/app/src/main/AndroidManifest.xml','android-transfer-bench/app/src/main/AndroidManifest.xml','evaluation/android-observer/app/src/main/AndroidManifest.xml']]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def gate():
    if adb(SERIAL,'emu','avd','name').splitlines()[0].strip()!='Task3Workflows':raise RuntimeError('WRONG_AVD')
    raw=adb(SERIAL,'shell','dumpsys','package',PROBE)
    if not re.search(r'\bversionCode=40\b',raw):raise RuntimeError('WRONG_PROBE_VERSION')
    path=adb(SERIAL,'shell','pm','path',PROBE).strip().removeprefix('package:')
    installed=adb(SERIAL,'shell','sha256sum',path).split()[0]
    apk=ROOT/'android-agent-probe/build/manual/demo-probe-v40-failure-context.apk'
    if installed!=hashlib.sha256(apk.read_bytes()).hexdigest():raise RuntimeError('WRONG_APK')
    artifacts={PROBE:dict(version=40,apkSha256=installed)}
    for package,version,relative in [(APP,6,'android-transfer-bench/build/manual/transfer-bench-task3-v6.apk'),('edu.sydney.evaluation',4,'evaluation/android-observer/build/manual/observer-task3-v4.apk')]:
        package_info=adb(SERIAL,'shell','dumpsys','package',package)
        if not re.search(r'\bversionCode='+str(version)+r'\b',package_info):raise RuntimeError('WRONG_AUXILIARY_VERSION:'+package)
        location=adb(SERIAL,'shell','pm','path',package).strip().removeprefix('package:')
        sha=adb(SERIAL,'shell','sha256sum',location).split()[0]
        if sha!=hashlib.sha256((ROOT/relative).read_bytes()).hexdigest():raise RuntimeError('WRONG_AUXILIARY_APK:'+package)
        artifacts[package]=dict(version=version,apkSha256=sha)
    return dict(avd='Task3Workflows',device=SERIAL,version=40,apkSha256=installed,artifacts=artifacts,paidCalls=0)


def record(flow,out):
    out.mkdir(parents=True,exist_ok=False);case=FLOWS[flow]
    native.fixture(case,INITIALS[0]);prepare_teaching(language='en')
    text(SERIAL,'teachName','T3 '+flow);text(SERIAL,'teachGoal','Execute the observed '+flow+' process; preserve intermediate saves and cancellations.')
    before=optional_prefs();write(out/'before.json',before)
    tap(SERIAL,'teachRecord');tap(SERIAL,'button1','android')
    end=time.monotonic()+12
    while time.monotonic()<end:
        t=private(SERIAL,PROBE,'workflow-trace.json')
        if t.get('error'):raise RuntimeError('BASELINE:'+t['error'])
        if t.get('initial'):break
        time.sleep(.2)
    else:raise RuntimeError('BASELINE_TIMEOUT')
    for n,key in enumerate(case['actions'],1):
        native.target_tap(key);end=time.monotonic()+7
        while time.monotonic()<end:
            t=private(SERIAL,PROBE,'workflow-trace.json')
            if t.get('error'):raise RuntimeError('RECORDING:'+t['error'])
            if len(t['steps'])==n:break
            time.sleep(.15)
        else:raise RuntimeError('RECORDING_CONFIRMATION:'+key)
    home(SERIAL);tap(SERIAL,'teachEntry');tap(SERIAL,'teachStop')
    t=private(SERIAL,PROBE,'workflow-trace.json');write(out/'trace.json',t)
    expected=compile_evidence(t)
    if t['source']!='AUTOMATED' or [s['id'] for s in t['steps']]!=case['actions']:raise RuntimeError('REAL_RECORDING_DIFFERS')
    tap(SERIAL,'teachGenerate');end=time.monotonic()+8
    while time.monotonic()<end:
        state=prefs(SERIAL,'teaching_journey')
        if json.loads(state.get('draft','null'))==expected:break
        time.sleep(.15)
    else:raise RuntimeError('NATIVE_COMPILE_DIFFERS')
    if optional_prefs().get('approved')!=before.get('approved'):raise RuntimeError('COMPILE_GRANTED_APPROVAL')
    write(out/'skill.json',expected);snap(SERIAL,out/'guide.png')
    ui=tree(SERIAL);guide=next(n.get('text','') for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/teachGuide')
    (out/'guide.txt').write_text(guide,encoding='utf-8')
    management_control('teachSave');review_controls(tree(SERIAL));snap(SERIAL,out/'review-dialog.png');tap(SERIAL,'button1','android');saved=await_approved(expected)
    library(SERIAL);reopened=prefs(SERIAL)
    matches=[e for e in json.loads(reopened['library']) if e['name']=='T3 '+flow and e['skill']==expected]
    if len(matches)!=1 or json.loads(reopened['approved'])!=expected:raise RuntimeError('REOPENED_REVIEW_DIFFERS')
    write(out/'package.json',matches[0]);write(out/'reviewed.json',saved)
    print('RECORDED '+flow+' '+str(len(expected['steps']))+' genuine AUTOMATED steps; normal review',flush=True)
    return expected


def qualify(flow,source,out):
    """Re-use exact recorded evidence after UI repair; never fabricate another teaching."""
    t=json.loads((source/'trace.json').read_text(encoding='utf-8'));skill=json.loads((source/'skill.json').read_text(encoding='utf-8'))
    if compile_evidence(t)!=skill or t['source']!='AUTOMATED' or [s['id'] for s in t['steps']]!=FLOWS[flow]['actions']:raise RuntimeError('SOURCE_RECORDING_INVALID')
    current=prefs(SERIAL,'teaching_journey')
    if current.get('currentTrace')!=t['traceId'] or json.loads(current.get('draft','null'))!=skill:raise RuntimeError('SOURCE_REVIEW_NOT_CURRENT')
    out.mkdir(parents=True,exist_ok=False)
    for name in ['trace.json','skill.json','guide.txt','guide.png']:shutil.copyfile(source/name,out/name)
    before=prefs(SERIAL);write(out/'before.json',before)
    home(SERIAL);tap(SERIAL,'teachEntry');management_control('teachSave');review_controls(tree(SERIAL));snap(SERIAL,out/'review-dialog.png')
    tap(SERIAL,'button2','android')
    if prefs(SERIAL).get('approved')!=before.get('approved'):raise RuntimeError('CANCEL_REVIEW_GRANTED_APPROVAL')
    management_control('teachSave');review_controls(tree(SERIAL));tap(SERIAL,'button1','android');saved=await_approved(skill)
    library(SERIAL);entries=json.loads(prefs(SERIAL)['library']);matches=[e for e in entries if e['skill']==skill and e['name']=='T3 '+flow]
    if len(matches)!=1:raise RuntimeError('QUALIFIED_SKILL_NOT_PERSISTENT')
    write(out/'package.json',matches[0]);write(out/'reviewed.json',saved)
    write(out/'qualification.json',dict(originalSource=str(source),reRecorded=False,skillAndTraceUnchanged=True,normalReview=True,cancelKeptApproval=True,paidCalls=0))
    print('QUALIFIED '+flow+' exact original recording; normal cancel/save; old failure retained',flush=True)


def fixture(skill,initial,fault='normal',wrong=False):
    import secrets
    case_id=secrets.token_hex(8);page='overview' if skill['version']<3 else skill['startPage']
    args=['--es','caseId',case_id,'--es','layout','single' if page=='single' else 'multi','--es','initial',','.join(map(str,initial)), '--es','fault',fault]
    if wrong:args+=['--es','startPage','lamp']
    adb(SERIAL,'shell','am','start','-W','-n',APP+'/.WorkflowActivity',*args)
    before=wait_fixture(lambda:private(SERIAL,APP,'workflow-oracle.json'),case_id,initial)
    if before['fault']!=fault:raise RuntimeError('FIXTURE_FAULT_DIFFERS')
    return case_id,before


def start_run(skill):
    entries=json.loads(prefs(SERIAL)['library']);matches=[i for i,e in enumerate(entries) if e['skill']==skill]
    if len(matches)!=1:raise RuntimeError('NO_UNIQUE_REVIEWED_SKILL')
    library(SERIAL);management_control('libraryRun'+str(matches[0]));review_controls(tree(SERIAL));tap(SERIAL,'button1','android')


def collect(skill,initial,case_id,out,previous):
    result=wait_terminal(lambda:private(SERIAL,PROBE,'recorded-workflow-result.json',timeout=5),previous,
        budget_seconds=16+6.5*len(skill['steps']))
    finished=time.monotonic();samples=[audited(SERIAL)['oracle']]
    for delay in [1,5]:
        rest=finished+delay-time.monotonic()
        if rest>0:time.sleep(rest)
        samples.append(audited(SERIAL)['oracle'])
    oracle=samples[-1]
    xml=ET.fromstring(adb(SERIAL,'shell','run-as',APP,'cat','shared_prefs/WorkflowActivity.xml'))
    disk=list(map(int,next(n.text for n in xml if n.get('name')=='committed').split(',')))
    journal=[json.loads(s) for s in adb(SERIAL,'shell','run-as',PROBE,'cat','files/workflow-journal-'+result['runId']+'.jsonl').splitlines() if s.strip()]
    for name,data in [('skill',skill),('result',result),('oracle',oracle),('journal',journal),('delayed-audits',samples),('disk',disk)]:write(out/(name+'.json'),data)
    return result,oracle,journal,samples,disk


def normal(row,skill,out):
    out.mkdir(parents=True,exist_ok=False);initial=row['initial'];case_id,before=fixture(skill,initial)
    write(out/'case.json',dict(row,caseId=case_id));write(out/'before.json',before)
    try:previous=private(SERIAL,PROBE,'recorded-workflow-result.json')['runId']
    except RuntimeError as error:
        if 'No such file' not in str(error):raise
        previous=None
    start_run(skill);result,oracle,journal,samples,disk=collect(skill,initial,case_id,out,previous)
    checked=judge(skill,initial,result,oracle,journal,samples,disk,case_id)
    write(out/'score.json',checked)
    print(row['id']+' '+('PASS' if checked['correctCompletion'] else 'NOT_CORRECT')+' '+str(checked['errors']),flush=True)
    return dict(id=row['id'],status='PASS' if checked['correctCompletion'] else ('FAIL' if checked['evidenceQualified'] else 'UNVERIFIED'),evidenceQualified=checked['evidenceQualified'],elapsedMs=checked['elapsedMs'],falseSuccess=checked['falseSuccess'])


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['record','confirm','qualify']);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--flow',choices=FLOWS,required=True);p.add_argument('--recording',type=Path);p.add_argument('--limit',type=int)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);rows=[];hashes=None
    try:
        write(a.output/'device.json',gate())
        hashes=source_hashes();write(a.output/'source-hashes.json',hashes)
        if a.mode=='record':record(a.flow,a.output/'recording');return
        if a.recording is None:p.error('Confirmation requires a saved real recording')
        if a.mode=='qualify':qualify(a.flow,a.recording,a.output/'recording');return
        skill=json.loads((a.recording/'skill.json').read_text(encoding='utf-8'))
        plan=[c for c in cases() if c.get('flow')==a.flow]
        random.Random(300731).shuffle(plan)
        if a.limit:plan=plan[:a.limit]
        write(a.output/'frozen-cases.json',plan)
        for row in plan:
            value=normal(row,skill,a.output/row['id']);rows.append(value);write(a.output/'rows.json',rows);write(a.output/'summary.json',summary(rows))
            if value['status']!='PASS':raise RuntimeError('CONFIRMATION_NOT_CORRECT')
    except Exception as error:
        write(a.output/'failure.json',dict(error=type(error).__name__,reason=str(error),paidCalls=0))
        try:snap(SERIAL,a.output/'failure.png')
        except Exception:pass
        raise
    finally:
        write(a.output/'preparation-reads.json',PREPARATION_READS)
        if hashes is not None:
            write(a.output/'source-stability.json',dict(sourceStable=source_hashes()==hashes,paidCalls=0))


def review_controls(ui):
    windows=list(ui)
    if len(windows)!=1:raise RuntimeError('REVIEW_WINDOW_NOT_UNIQUE')
    window=list(map(int,re.findall(r'-?\d+',windows[0].get('bounds',''))))
    if len(window)!=4:raise RuntimeError('REVIEW_WINDOW_BOUNDS_MISSING')
    for key in ['android:id/button1','android:id/button2']:
        nodes=[n for n in ui.iter('node') if n.get('resource-id')==key]
        if len(nodes)!=1:raise RuntimeError('REVIEW_CONTROL_NOT_UNIQUE')
        n=nodes[0];b=list(map(int,re.findall(r'-?\d+',n.get('bounds',''))))
        if (len(b)!=4 or not(window[0]<=b[0]<b[2]<=window[2] and window[1]<=b[1]<b[3]<=window[3])
            or n.get('enabled')!='true' or n.get('clickable')!='true'):raise RuntimeError('REVIEW_CONTROL_NOT_VISIBLE')
    return True


if __name__=='__main__':main()
