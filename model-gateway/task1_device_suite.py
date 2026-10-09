"""Task 1 installed emulator suites. Injected selection, real existing executor."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import secrets
import threading
import time
import xml.etree.ElementTree as ET
from entry_matrix import run as entry_run
from intent_bridge import BridgeServer
from named_journey_device import prefs,library,home,tap,text,snap,wait_fixture,APP,PROBE
from entry_phone import reverse_target,restore_input,read_input
from flexible_device_checks import CASES,score
from transfer_run import private,audited
from transfer_terminal_wait import wait_terminal
from workflow_capture import tree
from workflow_experiment import adb,write
from migration_matrix import display,effective_display_value
from user_robustness import restore_display

SERIAL='emulator-5554'
CONFIGS={'D0':('720x1280','240','1.0'),'D1':('540x960','240','1.0'),
         'D2':('1080x1920','320','1.0'),'D3':('720x1280','240','1.3')}
FAULTS={'missing-control':'missing','duplicate-control':'duplicate','dropped-input':'drop',
        'save-failure':None,'old-observation':None,'rollback':'rollback','disabled-control':None,
        'cancel':None,'foreground-change':None,'deadline-exhausted':None}


def initial_for(goal,condition):
    base=[0,40,0,3];wrong=[0 if goal[0]==1 else 1,40 if goal[1]!=40 else 80,0 if goal[2]==1 else 1,3 if goal[3]!=3 else 1]
    requested=[i for i,v in enumerate(goal) if v is not None]
    chosen=requested if condition=='all' else requested[:max(1,len(requested)//2)] if condition=='partial' and len(requested)>1 else []
    return [base[i] if v is None else v if i in chosen else wrong[i] for i,v in enumerate(goal)]


def make_execution_cases():
    rows=[];rng=random.Random(110034)
    for repeat in range(3):
        block=[dict(caseId=f'E-{name}-{condition}-{repeat}',suite='normal',skill=name,
                    condition=condition,repeat=repeat,fault='normal',automatable=True)
               for name in CASES for condition in ('none','partial','all')]
        rng.shuffle(block);rows.extend(block)
    for repeat in range(3):
        for name,fault in FAULTS.items():
            rows.append(dict(caseId=f'F-{name}-{repeat}',suite='fault',skill='single',
                             condition='none',repeat=repeat,fault=fault,automatable=fault is not None))
    return rows


def execution_verdict(value,negative,identity_ok,safety_ok):
    if not identity_ok or not safety_ok or value['falseSuccess'] or not value['untouched']:return 'FAIL'
    if negative:return 'PASS' if value['status']!='SUCCEEDED' else 'FAIL'
    return 'PASS' if value['correctCompletion'] else 'FAIL'


def injected_preview(name,skills,budget):
    chosen=[s for s in skills if s['name']==name]
    if len(chosen)!=1:raise RuntimeError('CATALOG_NAME_NOT_UNIQUE')
    return budget.call(lambda payload,timeout:dict(status='invoke',skill_id=chosen[0]['id'],
        message='Injected saved-workflow selection; not model accuracy.'),{},'INJECTED')


def display_suite(out):
    out.mkdir(parents=True,exist_ok=False);original=display(SERIAL)
    font=adb(SERIAL,'shell','settings','get','system','font_scale').strip()
    if font=='null':raise RuntimeError('FONT_SCALE_NOT_READABLE')
    write(out/'protocol.json',dict(configs=CONFIGS,planned=96,modelCalls=0,originalDisplay=original,originalFont=font))
    rows=[]
    try:
        for key,(size,dpi,scale) in CONFIGS.items():
            adb(SERIAL,'shell','wm','size',size);adb(SERIAL,'shell','wm','density',dpi)
            adb(SERIAL,'shell','settings','put','system','font_scale',scale);time.sleep(1)
            actual=display(SERIAL);actual_font=adb(SERIAL,'shell','settings','get','system','font_scale').strip()
            write(out/(key+'-display.json'),dict(**actual,fontScale=actual_font))
            if effective_display_value(actual['size'])!=size or effective_display_value(actual['density'])!=dpi or float(actual_font)!=float(scale):
                raise RuntimeError('DISPLAY_READBACK_MISMATCH:'+key)
            try:value=entry_run(SERIAL,out/key,2,True)
            except Exception:
                partial=out/key/'summary.json'
                if partial.exists():
                    value=json.loads(partial.read_text(encoding='utf-8'))
                    rows.append(dict(config=key,completed=False,**value));write(out/'results.json',rows)
                raise
            rows.append(dict(config=key,completed=True,**value));write(out/'results.json',rows)
            print('DISPLAY '+key+' '+json.dumps(value),flush=True)
    finally:
        restore_display(SERIAL,original);adb(SERIAL,'shell','settings','put','system','font_scale',font)
        restored=display(SERIAL)==original and adb(SERIAL,'shell','settings','get','system','font_scale').strip()==font
        write(out/'restored.json',dict(displayAndFontRestored=restored))
        write(out/'summary.json',dict(planned=96,attempted=sum(r['attempted'] for r in rows),
            passed=sum(r['passed'] for r in rows),failed=sum(r['failed'] for r in rows),
            harnessErrors=sum(r.get('harnessErrors',0) for r in rows),
            notRun=96-sum(r['attempted'] for r in rows),modelCalls=0,restored=restored))
        if not restored:raise RuntimeError('DISPLAY_RESTORATION_FAILED')


def saved_entries():
    entries=json.loads(prefs(SERIAL)['library']);found={}
    for name,case in CASES.items():
        matches=[e for e in entries if e['skill']['version']==3 and [s['id'] for s in e['skill']['steps']]==case['actions']]
        if not matches:raise RuntimeError('EXISTING_SKILL_NOT_FOUND:'+name)
        found[name]=matches[-1]
    return entries,found


def execute_one(case,item,out,server):
    out.mkdir(parents=True,exist_ok=False);skill=item['skill'];initial=initial_for(skill['finalGoals'],case['condition'])
    case_id=secrets.token_hex(8);write(out/'case.json',dict(case,initial=initial,fixtureCaseId=case_id));write(out/'skill.json',skill)
    previous=private(SERIAL,PROBE,'recorded-workflow-result.json')
    if previous.get('status')=='RUNNING':raise RuntimeError('PREVIOUS_TASK_RUNNING')
    adb(SERIAL,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','caseId',case_id,
        '--es','layout','single' if skill['startPage']=='single' else 'multi','--es','initial',','.join(map(str,initial)),
        '--es','fault',case['fault'])
    before=wait_fixture(lambda:private(SERIAL,APP,'workflow-oracle.json'),case_id,initial)
    if before['fault']!=case['fault']:raise RuntimeError('FAULT_NOT_INJECTED')
    write(out/'before.json',before);library(SERIAL)
    server.chosen_name=item['name'];prior_ids=set(server.selection_events)
    command=('请执行已保存的流程：' if case['repeat']%2==0 else 'Run the saved ordered workflow: ')+item['name']
    text(SERIAL,'libraryInput',command);tap(SERIAL,'libraryChoose')
    ui=tree(SERIAL)
    if not any(n.get('resource-id')=='android:id/button1' for n in ui.iter('node')):
        snap(SERIAL,out/'no-confirmation.png')
        write(out/'selection-failure.json',dict(audit=server.selection_audit,
            statuses=[n.get('text','') for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/libraryStatus']))
        raise RuntimeError('NO_CONFIRMATION')
    if not any(item['name'] in n.get('text','') for n in ui.iter('node')):raise RuntimeError('WRONG_PREVIEW')
    preview_oracle=private(SERIAL,APP,'workflow-oracle.json')
    if preview_oracle!=before or private(SERIAL,PROBE,'recorded-workflow-result.json')!=previous:raise RuntimeError('INPUT_BEFORE_CONFIRMATION')
    ids=set(server.selection_events)-prior_ids
    if len(ids)!=1:raise RuntimeError('SELECTION_REQUEST_COUNT')
    identity=next(iter(ids));audit=[x for x in server.selection_audit if x['request_id']==identity]
    if len(audit)!=1 or audit[0]['outcome']!='invoke':raise RuntimeError('SELECTION_AUDIT_INCOMPLETE')
    write(out/'selection.json',dict(requestId=identity,audit=audit,command=command,source='INJECTED_NOT_MODEL_ACCURACY',targetInputsBeforeConfirmation=0))
    snap(SERIAL,out/'preview.png');tap(SERIAL,'button1','android')
    result=wait_terminal(lambda:private(SERIAL,PROBE,'recorded-workflow-result.json',timeout=4),previous.get('runId'),
                         budget_seconds=6+len(skill['steps'])*7+10)
    finished=time.monotonic();samples=[audited(SERIAL)]
    for delay in (1,5):
        left=finished+delay-time.monotonic()
        if left>0:time.sleep(left)
        samples.append(audited(SERIAL))
    oracle=samples[-1]['oracle'];write(out/'result.json',result);write(out/'audit.json',samples)
    journal=[json.loads(line) for line in adb(SERIAL,'shell','run-as',PROBE,'cat','files/workflow-journal-'+result['runId']+'.jsonl').splitlines() if line.strip()]
    write(out/'journal.json',journal)
    committed=next(n.text for n in ET.fromstring(adb(SERIAL,'shell','run-as',APP,'cat','shared_prefs/WorkflowActivity.xml')) if n.get('name')=='committed')
    write(out/'persistent.json',committed)
    identity_ok=(oracle['caseId']==case_id and oracle['fault']==case['fault'] and result['traceSha256']==skill['traceSha256']
        and result['traceId']==skill['traceId'] and result['requestedGoals']==skill['finalGoals']
        and result['goal']==[initial[i] if v is None else v for i,v in enumerate(skill['finalGoals'])]
        and [e['seq'] for e in journal]==list(range(1,len(journal)+1)) and all(e['runId']==result['runId'] for e in journal)
        and list(map(int,committed.split(',')))==oracle['events'][-1]['saved'])
    value=score(skill,initial,result,oracle,journal)
    allowed={s['id'] for s in skill['steps']};actions=result.get('actions',[])
    start,end=result['startedMs'],result['finishedMs']
    safety_ok=all(a['id'] in allowed and start<=a['ms']<=min(end,result['deadlineMs']) for a in actions)
    protected=[i for i,v in enumerate(skill['finalGoals']) if v is None]
    safety_ok &= all(all(e['saved'][i]==initial[i] and e['draft'][i]==initial[i] for i in protected) for e in oracle['events'] if e['ms']>=start)
    safety_ok &= (samples[0]['capturedMs']>=end and samples[-1]['capturedMs']-end>=5000
        and all(s['oracle']['caseId']==case_id and s['oracle']['events']==oracle['events'][:len(s['oracle']['events'])] for s in samples))
    row=dict(case=case,**value,identityOk=bool(identity_ok),safetyOk=bool(safety_ok),
        assessment=execution_verdict(value,case['suite']=='fault',identity_ok,safety_ok),modelCalls=0)
    write(out/'score.json',row);print('E2E '+case['caseId']+' '+row['assessment']+' '+row['status'],flush=True)
    return row


def execution_suite(out):
    out.mkdir(parents=True,exist_ok=False);original=prefs(SERIAL);prior=reverse_target(SERIAL)
    entries,selected=saved_entries();original_approved=json.loads(original['approved'])
    restore_item=next(e for e in entries if e['skill']==original_approved)
    token=prefs(SERIAL,'language_connection')['pairing'];library(SERIAL)
    saved=read_input(SERIAL)
    cases=make_execution_cases();rows=[]
    def select(command,skills,budget):
        return injected_preview(server.chosen_name,skills,budget)
    server=BridgeServer(('127.0.0.1',0),token,bounded_selector=select,max_calls=100);server.chosen_name=''
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    write(out/'protocol.json',dict(device=SERIAL,cases=cases,planned=75,selected=selected,sourceType='INJECTED_SELECTION_REAL_EXECUTION',
        originalLibrarySha256=hashlib.sha256(original['library'].encode()).hexdigest(),originalApproved=original_approved,
        sourceSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),modelCalls=0,
        deadline='Product budget unchanged; observer timeout is separate',restorationRunExcludedFromScores=True))
    try:
        adb(SERIAL,'reverse','tcp:8765','tcp:'+str(server.server_port))
        for index,case in enumerate(cases):
            folder=out/f'{index:02d}-{case["caseId"]}'
            if not case['automatable']:
                folder.mkdir();row=dict(case=case,assessment='NOT_RUN',reason='No matching non-destructive fixture injection',modelCalls=0)
                write(folder/'score.json',row)
            else:row=execute_one(case,selected[case['skill']],folder,server)
            rows.append(row);write(out/'results.json',rows)
        # Restore the active slot through ordinary preview/confirmation, not preference writes.
        restore_case=dict(caseId='RESTORE-ACTIVE-SLOT',suite='normal',condition='all',repeat=0,fault='normal')
        restore=execute_one(restore_case,restore_item,out/'restoration-run',server)
        write(out/'restoration-run-score.json',restore)
    except Exception as error:
        write(out/'failure.json',dict(error=type(error).__name__,reason=str(error),scored=len(rows)));raise
    finally:
        if prefs(SERIAL).get('approved')!=original.get('approved'):
            restore_case=dict(caseId='RESTORE-ACTIVE-SLOT-FINALLY',suite='normal',condition='all',repeat=0,fault='normal')
            try:execute_one(restore_case,restore_item,out/'restoration-finally',server)
            except Exception as error:write(out/'restoration-error.json',dict(error=type(error).__name__,reason=str(error)))
        server.shutdown();server.server_close();worker.join(3)
        if prior:adb(SERIAL,'reverse','tcp:8765',prior)
        else:adb(SERIAL,'reverse','--remove','tcp:8765')
        restored_input=restore_input(SERIAL,saved);after=prefs(SERIAL)
        restored=dict(inputRestored=restored_input,libraryUnchanged=after['library']==original['library'],
            originalApprovedRestored=after.get('approved')==original.get('approved'),reverseRestored=reverse_target(SERIAL)==prior,
            resultIsNewAuditedTestHistory=True)
        write(out/'restored.json',restored)
        write(out/'summary.json',dict(planned=75,attempted=sum(r['assessment']!='NOT_RUN' for r in rows),
            passed=sum(r['assessment']=='PASS' for r in rows),failed=sum(r['assessment']=='FAIL' for r in rows),
            notRun=75-sum(r['assessment']!='NOT_RUN' for r in rows),
            normalCompleted=sum(r.get('correctCompletion',False) for r in rows if r['case']['suite']=='normal'),
            falseSuccess=sum(r.get('falseSuccess',False) for r in rows),modelCalls=0,**restored))
        if not all(restored[k] for k in ('inputRestored','libraryUnchanged','originalApprovedRestored','reverseRestored')):
            raise RuntimeError('E2E_RESTORATION_NOT_VERIFIED')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['display','execution']);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();(display_suite if args.mode=='display' else execution_suite)(args.output)
