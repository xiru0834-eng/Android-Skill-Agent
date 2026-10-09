"""Controlled interruption experiments, isolated emulator only, no model calls."""
import argparse
import base64
import hashlib
import json
import secrets
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from flexible_device_checks import SERIAL, CASES, INITIALS, fixture, reconnect_experiment_service, target_tap
from named_journey_device import home, tap, prefs, snap, text
from transfer_run import private
from workflow_capture import APP, PROBE, tree
from workflow_contract import compile_evidence, WorkflowError
from workflow_experiment import adb, write


def read_result():return private(SERIAL,PROBE,'recorded-workflow-result.json',timeout=4)
def inputs(oracle):return [e for e in oracle['events'] if e['kind'].startswith(('input:','edit:'))]
def oracle():return private(SERIAL,APP,'workflow-oracle.json',timeout=4)

def no_late_inputs(result,state):
    """Terminal and App ledger share elapsedRealtime within the same execution boot."""
    end=result.get('finishedMs')
    return type(end) is int and end>=0 and all(type(e.get('ms')) is int and e['ms']<=end for e in inputs(state))

def stop_passed(before,after,state,stopped,latest,unchanged):
    return (after['runId']==before['runId'] and after['status']=='CANCELLED'
        and after['reason']=='USER_OR_SERVICE_STOP' and len(inputs(latest))==len(inputs(stopped))
        and state['caseId']==stopped['caseId']==latest['caseId'] and unchanged and no_late_inputs(after,latest))

def recording_passed(scenario,before,after,state,stopped,latest,unchanged,compiler_rejected,generate_blocked,archive_ok):
    expected={'record-cancel':('CANCELLED',''),'record-leave':('REJECTED','LEFT_ALLOWED_APPS'),
              'record-kill':('INTERRUPTED','PROCESS_RESTARTED')}[scenario]
    return (after['traceId']==before['traceId'] and before['end']=='RECORDING'
        and before['source']==after['source']=='AUTOMATED' and before['steps']==after['steps']
        and (after['end'],after['error'])==expected
        and state['caseId']==stopped['caseId']==latest['caseId']
        and len(inputs(latest))==len(inputs(stopped)) and unchanged and compiler_rejected
        and generate_blocked and (scenario!='record-kill' or archive_ok))

def leave_passed(before,after,state,stopped,latest,unchanged):
    return (after['runId']==before['runId'] and after['status']=='UNCONFIRMED'
        and after['reason']=='WRONG_APP' and len(inputs(latest))==len(inputs(stopped))
        and state['caseId']==stopped['caseId']==latest['caseId'] and unchanged and no_late_inputs(after,latest))

def assess_kill(before,after,state,stopped,latest,unchanged,archived):
    no_more=len(inputs(latest))==len(inputs(stopped))
    same_case=state['caseId']==stopped['caseId']==latest['caseId']
    recovery=after.get('recovery',{})
    sealed=(after['runId']==before['runId'] and after['status']=='UNCONFIRMED'
            and after['reason']=='SERVICE_RECONNECTED' and recovery.get('noAutomaticResume') is True
            and recovery.get('scope')=='LAST_PERSISTED_CHECKPOINT_ONLY')
    return dict(assessmentPassed=sealed and same_case and no_more and unchanged and archived,
                status=after['status'],reason=after['reason'],inputsBeforeKill=len(inputs(state)),
                inputsAtStop=len(inputs(stopped)),postStopExtraInputs=len(inputs(latest))-len(inputs(stopped)),
                approvalUnchanged=unchanged,checkpointArchived=archived,caseUnchanged=same_case)


def prepare_run():
    skill=json.loads(prefs(SERIAL)['approved'])
    if [s['id'] for s in skill['steps']]!=CASES['brightness']['actions']:
        raise RuntimeError('This interruption protocol needs the reviewed brightness skill')
    case_id=fixture(CASES['brightness'],INITIALS[0],fault='navdelay')
    home(SERIAL);tap(SERIAL,'teachEntry');tap(SERIAL,'teachLibraryToggle')
    old=read_result()['runId'];tap(SERIAL,'teachRun');tap(SERIAL,'button1','android')
    return skill,old,case_id

def wait_input(old,case_id):
    end=time.monotonic()+12
    while time.monotonic()<end:
        result=read_result();state=oracle()
        if result['runId']!=old and state['caseId']==case_id and inputs(state):
            if result['status']!='RUNNING':raise RuntimeError('Injection missed active execution')
            return result,state
        time.sleep(.03)
    raise RuntimeError('No active input for interruption')

def begin_run():
    skill,old,case_id=prepare_run();result,state=wait_input(old,case_id)
    return skill,result,state


def execute_kill(out):
    out.mkdir(parents=True,exist_ok=False)
    approved_before=prefs(SERIAL)['approved']
    skill,result,state=begin_run()
    write(out/'protocol.json',dict(scenario='execute_kill',source='AUTOMATED',modelCalls=0,
                                  appPackage=APP,runId=result['runId'],caseId=state['caseId']))
    write(out/'skill.json',skill);write(out/'result-before.json',result);write(out/'oracle-before.json',state)
    raw=adb(SERIAL,'shell','run-as',PROBE,'cat','files/workflow-journal-'+result['runId']+'.jsonl')
    write(out/'journal-before.json',[json.loads(line) for line in raw.splitlines() if line.strip()])
    adb(SERIAL,'shell','am','force-stop',PROBE)
    stopped=oracle();write(out/'oracle-stopped.json',stopped)
    reconnect_experiment_service()
    time.sleep(2)
    recovered=read_result();after=oracle()
    write(out/'result-after.json',recovered);write(out/'oracle-after.json',after)
    unchanged=prefs(SERIAL)['approved']==approved_before
    archived=False
    recovery=recovered.get('recovery',{})
    if recovery:
        expected='workflow-recovery-run-'+result['runId']+'-original.json'
        if recovery.get('originalFile')!=expected:raise RuntimeError('Unexpected recovery evidence location')
        original=adb(SERIAL,'shell','run-as',PROBE,'cat','files/'+expected)
        archived=json.loads(original)==result and hashlib.sha256(original.encode()).hexdigest()==recovery.get('originalSha256')
        write(out/'checkpoint-original.json',json.loads(original))
    judged=assess_kill(result,recovered,state,stopped,after,unchanged,archived)
    write(out/'score.json',judged)
    home(SERIAL);tap(SERIAL,'teachEntry');tap(SERIAL,'teachLibraryToggle');snap(SERIAL,out/'recovered.png')
    print(json.dumps(judged),flush=True)
    return judged


def execute_leave(out):
    """Move to system Settings after the first input; never operate Settings controls."""
    out.mkdir(parents=True,exist_ok=False)
    approved_before=prefs(SERIAL)['approved']
    skill,result,state=begin_run()
    write(out/'protocol.json',dict(scenario='execute_leave',source='AUTOMATED',modelCalls=0,
                                  runId=result['runId'],caseId=state['caseId']))
    write(out/'skill.json',skill);write(out/'result-before.json',result);write(out/'oracle-before.json',state)
    requested=time.monotonic()
    adb(SERIAL,'shell','am','start','-W','-a','android.settings.SETTINGS')
    deadline=time.monotonic()+8
    terminal=read_result()
    while terminal['status']=='RUNNING' and time.monotonic()<deadline:
        time.sleep(.1);terminal=read_result()
    stopped=oracle();time.sleep(2);latest=oracle()
    unchanged=prefs(SERIAL)['approved']==approved_before
    judged=dict(status=terminal['status'],reason=terminal['reason'],
                postStopExtraInputs=len(inputs(latest))-len(inputs(stopped)),
                inputsBeforeLeave=len(inputs(state)),inputsAtStop=len(inputs(stopped)),
                approvalUnchanged=unchanged,caseUnchanged=state['caseId']==stopped['caseId']==latest['caseId'],
                requestToFinalObservationMs=round((time.monotonic()-requested)*1000))
    judged['assessmentPassed']=leave_passed(result,terminal,state,stopped,latest,unchanged)
    write(out/'result-after.json',terminal);write(out/'oracle-stopped.json',stopped)
    write(out/'oracle-after.json',latest);write(out/'score.json',judged)
    raw=adb(SERIAL,'shell','run-as',PROBE,'cat','files/workflow-journal-'+result['runId']+'.jsonl')
    write(out/'journal.json',[json.loads(line) for line in raw.splitlines() if line.strip()])
    snap(SERIAL,out/'stopped.png')
    print(json.dumps(judged),flush=True)
    return judged


def begin_recording():
    """Complete a teachable route but keep recording active for the fault injection."""
    fixture(CASES['brightness'],INITIALS[0])
    home(SERIAL);tap(SERIAL,'homeAdvanced');tap(SERIAL,'guidedTest')
    if prefs(SERIAL,'teaching_journey').get('currentTrace'):tap(SERIAL,'teachNew')
    text(SERIAL,'teachName','Interruption '+secrets.token_hex(3))
    text(SERIAL,'teachGoal','Set reading lamp brightness to sixty percent and save.')
    tap(SERIAL,'teachRecord');tap(SERIAL,'button1','android')
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        trace=private(SERIAL,PROBE,'workflow-trace.json')
        if trace.get('error'):raise RuntimeError('Baseline rejected '+trace['error'])
        if trace.get('initial'):break
        time.sleep(.2)
    else:raise RuntimeError('Recording baseline unavailable')
    for count,key in enumerate(CASES['brightness']['actions'],1):
        target_tap(key);deadline=time.monotonic()+7
        while time.monotonic()<deadline:
            trace=private(SERIAL,PROBE,'workflow-trace.json')
            if trace.get('error'):raise RuntimeError('Recording action rejected '+trace['error'])
            if len(trace['steps'])==count:time.sleep(.3);break
            time.sleep(.2)
        else:raise RuntimeError('Recording action not confirmed '+key)
    if trace['end']!='RECORDING' or trace['source']!='AUTOMATED':raise RuntimeError('Missed active recording')
    # Counterfactual proves the same complete steps would compile if normally finished.
    normally_finished=dict(trace,end='STOPPED');compile_evidence(normally_finished)
    return trace,oracle()


def record_interrupt(out,scenario):
    out.mkdir(parents=True,exist_ok=False);approved_before=prefs(SERIAL)['approved']
    before,state=begin_recording()
    write(out/'protocol.json',dict(scenario=scenario,source='AUTOMATED',modelCalls=0,
        traceId=before['traceId'],caseId=state['caseId'],completeRouteBeforeInterruption=True))
    write(out/'trace-before.json',before);write(out/'oracle-before.json',state)
    audit_name='workflow-audit-'+before['traceId']+'.json'
    audit_before=private(SERIAL,PROBE,audit_name);write(out/'audit-before.json',audit_before)
    requested=time.monotonic()
    if scenario=='record-cancel':
        home(SERIAL);tap(SERIAL,'teachEntry');tap(SERIAL,'teachCancel');tap(SERIAL,'button1','android')
    elif scenario=='record-leave':
        adb(SERIAL,'shell','am','start','-W','-a','android.settings.SETTINGS')
    else:
        adb(SERIAL,'shell','am','force-stop',PROBE);reconnect_experiment_service()
    deadline=time.monotonic()+8
    after=private(SERIAL,PROBE,'workflow-trace.json')
    while after['end']=='RECORDING' and time.monotonic()<deadline:
        time.sleep(.1);after=private(SERIAL,PROBE,'workflow-trace.json')
    stopped=oracle();time.sleep(2);latest=oracle()
    write(out/'trace-after.json',after);write(out/'oracle-stopped.json',stopped);write(out/'oracle-after.json',latest)
    compiler_rejected=False
    try:compile_evidence(after)
    except WorkflowError:compiler_rejected=True
    archive_ok=True
    if scenario=='record-kill':
        recovery=private(SERIAL,PROBE,'workflow-recovery-trace-'+before['traceId']+'.json')
        name='workflow-recovery-trace-'+before['traceId']+'-original.json'
        original=adb(SERIAL,'shell','run-as',PROBE,'cat','files/'+name)
        archive_ok=(recovery['originalFile']==name and json.loads(original)==before
            and hashlib.sha256(original.encode()).hexdigest()==recovery['originalSha256']
            and private(SERIAL,PROBE,audit_name)==audit_before and recovery['noAutomaticResume'] is True)
        write(out/'recovery.json',recovery);write(out/'checkpoint-original.json',json.loads(original))
    home(SERIAL);tap(SERIAL,'teachEntry');ui=tree(SERIAL)
    generate=[n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/teachGenerate']
    blocked=not generate or all(n.get('enabled')!='true' for n in generate)
    unchanged=prefs(SERIAL)['approved']==approved_before
    passed=recording_passed(scenario,before,after,state,stopped,latest,unchanged,compiler_rejected,blocked,archive_ok)
    judged=dict(assessmentPassed=passed,end=after['end'],error=after['error'],confirmedSteps=len(after['steps']),
        compilerRejected=compiler_rejected,generateBlocked=blocked,approvalUnchanged=unchanged,
        archiveVerified=archive_ok if scenario=='record-kill' else None,
        postStopExtraInputs=len(inputs(latest))-len(inputs(stopped)),
        requestToFinalObservationMs=round((time.monotonic()-requested)*1000))
    write(out/'audit-after.json',private(SERIAL,PROBE,audit_name));write(out/'score.json',judged)
    snap(SERIAL,out/'stopped.png');print(json.dumps(judged),flush=True)
    return judged


def overlay_stop_position():
    response=adb(SERIAL,'shell','am','instrument','-w','-e','probeOverlay','true','edu.sydney.evaluation/.Observer')
    encoded=re.search(r'INSTRUMENTATION_RESULT: xml=(\S+)',response)
    if not encoded:raise RuntimeError('Overlay observation unavailable')
    ui=ET.fromstring(base64.b64decode(encoded[1]));nodes=[n for n in ui.iter('node')
        if n.get('resource-id')==PROBE+':id/teachOverlayFinish' and n.get('enabled')=='true']
    if len(nodes)!=1:raise RuntimeError('Stop button missing or ambiguous')
    bounds=list(map(int,re.findall(r'-?\d+',nodes[0].get('bounds',''))))
    if len(bounds)!=4 or bounds[2]<=bounds[0] or bounds[3]<=bounds[1]:raise RuntimeError('Stop button not visible')
    return (bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2


def execute_stop(out):
    out.mkdir(parents=True,exist_ok=False);approved_before=prefs(SERIAL)['approved']
    skill,old,case_id=prepare_run();position=overlay_stop_position();result,state=wait_input(old,case_id)
    write(out/'protocol.json',dict(scenario='execute-stop',source='AUTOMATED',modelCalls=0,
        runId=result['runId'],caseId=case_id,stopControlPosition=position))
    write(out/'skill.json',skill);write(out/'result-before.json',result);write(out/'oracle-before.json',state)
    requested=time.monotonic();adb(SERIAL,'shell','input','tap',*position)
    deadline=time.monotonic()+8;after=read_result()
    while after['status']=='RUNNING' and time.monotonic()<deadline:
        time.sleep(.1);after=read_result()
    stopped=oracle();time.sleep(2);latest=oracle();unchanged=prefs(SERIAL)['approved']==approved_before
    judged=dict(assessmentPassed=stop_passed(result,after,state,stopped,latest,unchanged),
        status=after['status'],reason=after['reason'],approvalUnchanged=unchanged,
        inputsAtStop=len(inputs(stopped)),postStopExtraInputs=len(inputs(latest))-len(inputs(stopped)),
        requestToFinalObservationMs=round((time.monotonic()-requested)*1000))
    write(out/'result-after.json',after);write(out/'oracle-stopped.json',stopped);write(out/'oracle-after.json',latest)
    raw=adb(SERIAL,'shell','run-as',PROBE,'cat','files/workflow-journal-'+result['runId']+'.jsonl')
    write(out/'journal.json',[json.loads(line) for line in raw.splitlines() if line.strip()]);write(out/'score.json',judged)
    snap(SERIAL,out/'stopped.png');print(json.dumps(judged),flush=True)
    return judged


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--repeat',type=int,default=1);p.add_argument('--reconnect-service',action='store_true')
    scenarios=['execute-stop','execute-leave','execute-kill','record-cancel','record-leave','record-kill']
    p.add_argument('--scenario',choices=scenarios+['matrix'],default='execute-kill');a=p.parse_args()
    if not 1<=a.repeat<=3:raise ValueError('Experiment repetition must be 1..3')
    a.output.mkdir(parents=True,exist_ok=False)
    if a.reconnect_service:reconnect_experiment_service()
    rows=[]
    for scenario in (scenarios if a.scenario=='matrix' else [a.scenario]):
        for i in range(a.repeat):
            case_out=a.output/(scenario+'-'+str(i))
            try:
                if scenario.startswith('record-'):judged=record_interrupt(case_out,scenario)
                else:judged={'execute-kill':execute_kill,'execute-leave':execute_leave,'execute-stop':execute_stop}[scenario](case_out)
            except Exception as error:
                write(a.output/'preparation-or-runtime-failure.json',dict(scenario=scenario,index=i,error=type(error).__name__,reason=str(error)))
                raise
            rows.append(dict(scenario=scenario,index=i,**judged));write(a.output/'results.json',rows)
            if a.scenario=='matrix' and not judged['assessmentPassed']:raise SystemExit(1)
    if not all(r['assessmentPassed'] for r in rows):raise SystemExit(1)


if __name__=='__main__':main()
