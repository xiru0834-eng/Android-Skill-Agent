"""Run the reviewed phone workflow through its real UI; oracle is evaluation-only."""
import argparse
import hashlib
import json
import random
import secrets
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from workflow_capture import APP, PROBE, workbench, click
from workflow_experiment import adb, write
from transfer_audit import evaluate
from transfer_cases import make_cases
from transfer_terminal_wait import wait_terminal

INITIALS=[[0,40,0,3],[1,60,0,3],[0,40,1,1],[1,40,1,3],[0,60,0,1],[1,60,1,1]]

def private(serial,package,name,timeout=40):
    if package not in (APP,PROBE):raise ValueError('Out of scope')
    return json.loads(adb(serial,'shell','run-as',package,'cat','files/'+name,timeout=timeout))

def approved(serial):
    rows=ET.fromstring(adb(serial,'shell','run-as',PROBE,'cat','shared_prefs/recorded_workflows.xml'))
    return json.loads(next(n.text for n in rows if n.get('name')=='approved'))

def audited(serial):
    response=adb(serial,'shell','am','broadcast','-n',APP+'/.WorkflowAuditReceiver')
    if 'result=-1' not in response:raise RuntimeError('Audit receiver unavailable')
    data=private(serial,APP,'workflow-oracle.json')
    if data['events'][-1]['kind']!='audit_snapshot':raise RuntimeError('No fresh audit event')
    return dict(capturedMs=data['events'][-1]['ms'],oracle=data)

def run(serial,case,directory,skill):
    directory.mkdir();case_id=secrets.token_hex(8);write(directory/'case.json',dict(case,caseId=case_id))
    if approved(serial)!=skill:raise RuntimeError('Approved skill changed')
    try:previous=private(serial,PROBE,'recorded-workflow-result.json')
    except RuntimeError as error:
        if 'No such file' not in str(error):raise
        previous={}
    if previous.get('status')=='RUNNING':raise RuntimeError('Previous execution still running; fixture not reset')
    adb(serial,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','caseId',case_id,'--es','layout','multi',
        '--es','initial',','.join(map(str,case['initial'])),'--es','fault',case['fault'])
    time.sleep(.4);before=private(serial,APP,'workflow-oracle.json');write(directory/'before.json',before)
    if before['caseId']!=case_id or before['initial']!=case['initial'] or before.get('fault')!=case['fault']:
        raise RuntimeError('Fixture preparation mismatch')
    entry_operator=workbench(serial)
    try:old=private(serial,PROBE,'recorded-workflow-result.json').get('runId')
    except Exception:old=None
    started=time.monotonic();operator=click(serial,'flowRun')
    write(directory/'operator-start.json',dict(harnessVersion='H3.1',postClickCollectionSeconds=35,operator=operator,entryOperator=entry_operator))
    result=wait_terminal(lambda:private(serial,PROBE,'recorded-workflow-result.json',timeout=2),old)
    ui_finished=time.monotonic();write(directory/'terminal.json',result)
    if result['traceId']!=skill['traceId'] or result['goal']!=skill['finalGoals']:raise RuntimeError('Wrong workflow ran')
    audits=[audited(serial)]
    for wait in (1,5):
        remaining=ui_finished+wait-time.monotonic()
        if remaining>0:time.sleep(remaining)
        audits.append(audited(serial))
    write(directory/'audit.json',audits);oracle=audits[-1]['oracle'];write(directory/'oracle.json',oracle)
    if oracle['caseId']!=case_id or oracle.get('fault')!=case['fault']:raise RuntimeError('Session reset by normal UI launch')
    prefs=ET.fromstring(adb(serial,'shell','run-as',APP,'cat','shared_prefs/WorkflowActivity.xml'))
    persisted=next(n.text for n in prefs if n.get('name')=='committed')
    write(directory/'persisted.json',persisted)
    if list(map(int,persisted.split(',')))!=oracle['events'][-1]['saved']:raise RuntimeError('Persistence mismatch')
    raw=adb(serial,'shell','run-as',PROBE,'cat','files/workflow-journal-'+result['runId']+'.jsonl')
    journal=[json.loads(line) for line in raw.splitlines() if line.strip()];write(directory/'journal.json',journal)
    if not journal or [e['seq'] for e in journal]!=list(range(1,len(journal)+1)) or any(e['runId']!=result['runId'] for e in journal):
        raise RuntimeError('Journal identity or sequence mismatch')
    judged=evaluate(oracle,result,skill['finalGoals'],audits,case_id=case_id,run_id=result['runId'])
    judged.update(reason=result['reason'],ui_completion_ms=round((ui_finished-started)*1000),case=case,harnessVersion='H3.1')
    write(directory/'score.json',judged)
    return judged

def main():
    p=argparse.ArgumentParser();p.add_argument('--device',choices=['R5CW134LLBZ','emulator-5554'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--repeats',type=int,choices=range(1,21),default=1)
    p.add_argument('--suite',choices=['normal','challenge'],default='normal');p.add_argument('--limit',type=int)
    p.add_argument('--allow-experiment',action='store_true');a=p.parse_args()
    if not a.allow_experiment:p.error('Explicit experiment consent required')
    a.output.mkdir(parents=True,exist_ok=False);skill=approved(a.device);write(a.output/'skill.json',skill)
    cases=make_cases(a.suite,a.repeats)
    if a.limit:cases=cases[:a.limit]
    write(a.output/'protocol.json',dict(device=a.device,suite=a.suite,cases=cases,seed=91284,budgetMs=30000,
          modelCalls=0,execution='Reviewed WorkflowActivity flowRun',humanDemonstration=False,harnessVersion='H3.1',
          sourceHashes={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                        for name in ('transfer_run.py','transfer_terminal_wait.py','workflow_capture.py','transfer_input_ready.py')}))
    results=[]
    for index,case in enumerate(cases):
        directory=a.output/f'run-{index:03d}'
        try:value=run(a.device,case,directory,skill)
        except Exception as error:
            value=dict(case=case,infrastructureFailure=str(error),evidence_complete=False)
            write(directory/'failure.json',value);results.append(value);write(a.output/'results.json',results)
            print(json.dumps(dict(index=index,**value)),flush=True)
            raise
        results.append(value);write(a.output/'results.json',results)
        print(json.dumps(dict(index=index,status=value['status'],confirmed=value['confirmed_success'],reason=value['reason'],ms=value['elapsed_ms'])),flush=True)
    summary=dict(planned=len(cases),executed=len(results),confirmed=sum(r['confirmed_success'] for r in results),
        false_success=sum(r['false_success'] for r in results),unconfirmed=sum(r['unconfirmed_success'] for r in results))
    write(a.output/'summary.json',summary);print(json.dumps(summary),flush=True)

if __name__=='__main__':main()
