"""Task 2 emulator-only operator. Normal recording/review; no private approvals."""
import argparse
import base64
import json
import re
import secrets
import time
import hashlib
import shutil
from pathlib import Path
import flexible_device_checks as native
from named_journey_device import home,tap,text,prefs,snap,library
from workflow_capture import tree,PROBE,APP
from workflow_experiment import adb,write
from transfer_run import private,audited
from transfer_terminal_wait import wait_terminal
from test_flexible_workflow import trace
from workflow_contract import compile_evidence
from task2_protocol import FLOWS,INITIALS,recording_match
from entry_preflight import application_service_state

SERIAL='emulator-5554'


def await_approved(skill,read=lambda:prefs(SERIAL),clock=time.monotonic,sleep=time.sleep,timeout=8):
    """Read-only acknowledgement wait; never repeats the user's Save input."""
    end=clock()+timeout
    while clock()<end:
        current=read()
        if clock()>=end:break
        if current.get('storageUnconfirmed')=='true':raise RuntimeError('SAVE_STORAGE_UNCONFIRMED')
        if (json.loads(current.get('approved','null'))==skill
            and any(e.get('skill')==skill for e in json.loads(current.get('library','[]')))):
            return current
        sleep(.2)
    raise RuntimeError('SAVE_ACKNOWLEDGEMENT_TIMEOUT')


def prepare_teaching(automated=True,language=None):
    home(SERIAL)
    if not application_service_state(tree(SERIAL)):raise RuntimeError('APPLICATION_SERVICE_NOT_READY')
    if automated:
        tap(SERIAL,'homeAdvanced');tap(SERIAL,'guidedTest')
    else:tap(SERIAL,'teachEntry')
    if prefs(SERIAL,'teaching_journey').get('currentTrace'):tap(SERIAL,'teachNew')
    if language:
        ui=tree(SERIAL);switch=next(n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/teachLanguage')
        current='zh' if switch.get('text')=='English' else 'en'
        if current!=language:tap(SERIAL,'teachLanguage')


def diagnostics(out):
    rows=[]
    for repeat in range(3):
        t=trace(['wfLampValue20','wfLampSave'],'single')
        payload=base64.b64encode(json.dumps(t,ensure_ascii=False).encode()).decode()
        raw=adb(SERIAL,'shell','am','instrument','-w','-e','trace',payload,PROBE+'/.TeachingChecks',timeout=50)
        (out/f'native-store-{repeat}.txt').write_text(raw,encoding='utf-8')
        match=re.search(r'PASS teaching checks=(\d+)',raw)
        if not match:raise RuntimeError('ISOLATED_NATIVE_STORE_CHECK_FAILED')
        rows.append(dict(repeat=repeat,checks=int(match[1]),isolatedPreferences=True,realDiskFailure=False))
    write(out/'results.json',rows)
    print('PASS native store diagnostics',rows,flush=True)


def inputs(out):
    prepare_teaching();before=prefs(SERIAL);old=private(SERIAL,PROBE,'workflow-trace.json');rows=[]
    for field,value in [('teachName','x'*60),('teachName','x'*61),('teachName','😀'*30),
                        ('teachName','😀'*31),('teachGoal','x'*240),('teachGoal','x'*241),
                        ('teachGoal','😀'*120),('teachGoal','😀'*121)]:
        text(SERIAL,'teachName','Task2 input checks');text(SERIAL,'teachGoal','No recording should start in this check.')
        text(SERIAL,field,value);ui=tree(SERIAL)
        nodes=[n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/'+field]
        exact=len(nodes)==1 and nodes[0].get('text')==value
        valid=sum(2 if ord(c)>65535 else 1 for c in value)<=(60 if field=='teachName' else 240)
        if not valid:
            tap(SERIAL,'teachRecord');ui=tree(SERIAL)
            dialogs=[n for n in ui.iter('node') if n.get('resource-id')=='android:id/button1']
            rejected=not dialogs and any('LENGTH' in n.get('text','') for n in ui.iter('node'))
        else:rejected=None
        unchanged=prefs(SERIAL)==before and private(SERIAL,PROBE,'workflow-trace.json')==old
        row=dict(field=field,utf16=sum(2 if ord(c)>65535 else 1 for c in value),rawExact=exact,
                 expectedValid=valid,invalidRejected=rejected,approvalAndEvidenceUnchanged=unchanged)
        rows.append(row);write(out/'results.json',rows)
        if not exact or not unchanged or (not valid and not rejected):raise RuntimeError('ACTUAL_METADATA_BOUNDARY_FAILED')
    snap(SERIAL,out/'input-error.png');print('PASS actual UI metadata boundaries: '+str(len(rows)),flush=True)


def record(flow,out):
    out.mkdir(parents=True,exist_ok=False);case=dict(page='overview',actions=FLOWS[flow])
    native.fixture(case,INITIALS[0]);prepare_teaching(language='en')
    name='T2 '+flow+' '+secrets.token_hex(3)
    text(SERIAL,'teachName',name);text(SERIAL,'teachGoal','Observed process '+flow+'; keep every saved intermediate state.')
    before=prefs(SERIAL);write(out/'workflow-before.json',before)
    tap(SERIAL,'teachRecord');tap(SERIAL,'button1','android')
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        t=private(SERIAL,PROBE,'workflow-trace.json')
        if t.get('error'):raise RuntimeError('BASELINE_REJECTED:'+t['error'])
        if t.get('initial'):break
        time.sleep(.2)
    else:raise RuntimeError('BASELINE_TIMEOUT')
    for count,key in enumerate(FLOWS[flow],1):
        native.target_tap(key);deadline=time.monotonic()+7
        while time.monotonic()<deadline:
            t=private(SERIAL,PROBE,'workflow-trace.json')
            if t.get('error'):raise RuntimeError('RECORDING_REJECTED:'+t['error'])
            if len(t['steps'])==count:break
            time.sleep(.2)
        else:raise RuntimeError('RECORDING_CONFIRMATION_TIMEOUT:'+key)
    home(SERIAL);tap(SERIAL,'teachEntry');tap(SERIAL,'teachStop')
    t=private(SERIAL,PROBE,'workflow-trace.json');write(out/'trace.json',t)
    start=time.monotonic();tap(SERIAL,'teachGenerate');p=prefs(SERIAL,'teaching_journey');skill=json.loads(p['draft'])
    compiled_ms=round((time.monotonic()-start)*1000,3)
    if not recording_match(t,skill,FLOWS[flow]):raise RuntimeError('COMPILED_PROCESS_MISMATCH')
    if prefs(SERIAL).get('approved')!=before.get('approved'):raise RuntimeError('COMPILE_APPROVED_WITHOUT_REVIEW')
    write(out/'skill.json',skill);snap(SERIAL,out/'guide.png')
    ui=tree(SERIAL);guide=next(n.get('text','') for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/teachGuide')
    (out/'guide.txt').write_text(guide,encoding='utf-8')
    tap(SERIAL,'teachSave');tap(SERIAL,'button1','android');saved=await_approved(skill)
    if json.loads(saved['approved'])!=skill:raise RuntimeError('SAVED_SKILL_MISMATCH')
    # A new Activity/Store must see the same ID, name and raw. No direct private writes.
    library(SERIAL);reopened=prefs(SERIAL)
    entries=json.loads(reopened['library']);matches=[e for e in entries if e['name']==name and e['skill']==skill]
    if len(matches)!=1:raise RuntimeError('REOPENED_SKILL_MISMATCH')
    write(out/'named-package.json',matches[0]);write(out/'workflow-after.json',reopened)
    write(out/'record-score.json',dict(recordingExact=True,compiledPersistent=True,source='AUTOMATED',
         normalApproval=True,modelCalls=0,steps=len(skill['steps']),compileUiRoundTripMs=compiled_ms,
         exportTested=False,differentDeviceTested=False))
    print('PASS recorded and reviewed '+flow+' steps='+str(len(skill['steps'])),flush=True)
    return skill


def qualified_existing_recording(flow,source,out):
    """Continue a saved, real recording after a test-observer race, never erase failure."""
    t=json.loads((source/'trace.json').read_text(encoding='utf-8'))
    skill=json.loads((source/'skill.json').read_text(encoding='utf-8'))
    if not recording_match(t,skill,FLOWS[flow]):raise RuntimeError('EXISTING_RECORDING_INVALID')
    current=await_approved(skill);entries=json.loads(current['library'])
    matches=[e for e in entries if e['skill']==skill]
    if len(matches)!=1:raise RuntimeError('EXISTING_RECORDING_NOT_UNIQUE')
    library(SERIAL);confirmed=prefs(SERIAL)
    if json.loads(confirmed['approved'])!=skill:raise RuntimeError('EXISTING_RECORDING_CHANGED_ON_REOPEN')
    out.mkdir(parents=True,exist_ok=False)
    for name in ['trace.json','skill.json','guide.txt','guide.png']:
        shutil.copyfile(source/name,out/name)
    write(out/'named-package.json',matches[0]);write(out/'workflow-after.json',confirmed)
    write(out/'qualification.json',dict(originalFailure=str(source.parent/'failure.json'),
          actualSavedSkillMatches=True,reopenedStoreMatches=True,repeatedSaveInputs=0,
          oldFailureRetained=True,newDemonstration=False,crossDevice=False,paidCalls=0))
    print('QUALIFIED existing recorded '+flow+'; first observer failure retained',flush=True)
    return skill


def replay(flow,skill,initial,out):
    out.mkdir(parents=True,exist_ok=False);case=dict(page=skill['startPage'],actions=FLOWS[flow])
    case_id=native.fixture(case,initial);home(SERIAL);tap(SERIAL,'teachEntry')
    if json.loads(prefs(SERIAL).get('approved','null'))!=skill:raise RuntimeError('WRONG_ACTIVE_SKILL')
    previous=private(SERIAL,PROBE,'recorded-workflow-result.json').get('runId')
    tap(SERIAL,'teachLibraryToggle');tap(SERIAL,'teachRun');tap(SERIAL,'button1','android')
    result=wait_terminal(lambda:private(SERIAL,PROBE,'recorded-workflow-result.json'),previous,budget_seconds=70)
    if result['traceSha256']!=skill['traceSha256']:raise RuntimeError('WRONG_EXECUTED_SKILL')
    time.sleep(.5);oracle=audited(SERIAL)['oracle']
    if oracle['caseId']!=case_id:raise RuntimeError('FIXTURE_CHANGED')
    journal=[json.loads(line) for line in adb(SERIAL,'shell','run-as',PROBE,'cat','files/workflow-journal-'+result['runId']+'.jsonl').splitlines() if line.strip()]
    write(out/'case.json',dict(flow=flow,initial=initial,caseId=case_id,sameDevice=True,modelCalls=0))
    write(out/'skill.json',skill);write(out/'result.json',result);write(out/'oracle.json',oracle);write(out/'journal.json',journal)
    judged=native.score(skill,initial,result,oracle,journal);write(out/'score.json',judged)
    print('REPLAY '+flow+' '+json.dumps(judged),flush=True)
    if not judged['correctCompletion'] or judged['falseSuccess']:raise RuntimeError('REPLAY_NOT_CORRECT')
    return judged


def journey(out,only=None,repeats=1,resume=None):
    before=prefs(SERIAL);write(out/'protected-before.json',before);rows=[]
    try:
        home(SERIAL);ui=tree(SERIAL)
        library_entries=json.loads(before.get('library','[]'))
        if len(library_entries)>17:raise RuntimeError('INSUFFICIENT_LIBRARY_CAPACITY_WITHOUT_ERASING_OLD_SKILLS')
        for flow in ([only] if only else FLOWS):
            skill=qualified_existing_recording(flow,resume,out/(flow+'-recording')) if flow=='P' and resume else record(flow,out/(flow+'-recording'))
            for repeat in range(repeats):
                for index,initial in enumerate(INITIALS):
                    row=replay(flow,skill,initial,out/f'{flow}-i{index}-r{repeat}')
                    rows.append(dict(flow=flow,initialIndex=index,repeat=repeat,**row));write(out/'same-device-results.json',rows)
    finally:
        after=prefs(SERIAL);old=json.loads(before.get('library','[]'));current=json.loads(after.get('library','[]'))
        preserved=all(e in current for e in old)
        write(out/'original-library-preservation.json',dict(originalsPreserved=preserved,oldCount=len(old),newCount=len(current),
              approvalRestored=False,sameDeviceOnly=True,paidCalls=0))
        if not preserved:raise RuntimeError('ORIGINAL_LIBRARY_CHANGED')


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['checks','inputs','journey']);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--only',choices=FLOWS);p.add_argument('--repeats',type=int,choices=[1,3],default=1)
    p.add_argument('--resume-recording',type=Path)
    p.add_argument('--version',type=int,choices=[35,36],default=36);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    try:
        avd=adb(SERIAL,'emu','avd','name').splitlines()[0].strip()
        package=adb(SERIAL,'shell','dumpsys','package',PROBE)
        if avd!='PortableSkill' or not re.search(r'\bversionCode='+str(a.version)+r'\b',package):raise RuntimeError('EXPERIMENT_DEVICE_OR_VERSION_MISMATCH')
        installed_path=adb(SERIAL,'shell','pm','path',PROBE).strip().removeprefix('package:')
        installed_hash=adb(SERIAL,'shell','sha256sum',installed_path).split()[0]
        apk=Path(__file__).resolve().parents[1]/('android-agent-probe/build/manual/demo-probe-v'+str(a.version)+('-teaching-safe.apk' if a.version==35 else '-teaching-guide.apk'))
        if hashlib.sha256(apk.read_bytes()).hexdigest()!=installed_hash:raise RuntimeError('APK_MISMATCH')
        write(a.output/'run-protocol.json',dict(device=SERIAL,avd=avd,version=a.version,apkSha256=installed_hash,
             mode=a.mode,automated=True,repeats=a.repeats,paidCalls=0,noPrivateApprovalWrites=True))
        if a.mode=='checks':diagnostics(a.output)
        elif a.mode=='inputs':inputs(a.output)
        else:journey(a.output,a.only,a.repeats,a.resume_recording)
    except Exception as error:
        write(a.output/'failure.json',dict(error=type(error).__name__,reason=str(error),paidCalls=0))
        try:snap(SERIAL,a.output/'failure.png')
        except Exception:pass
        raise


if __name__=='__main__':main()
