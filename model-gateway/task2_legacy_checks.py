"""Task 2 end-to-end regression through old named-library buttons, emulator only."""
import argparse
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from named_journey_device import prefs,library,tap,snap
from workflow_capture import PROBE,APP
from workflow_experiment import adb,write
from flexible_device_checks import fixture,score as process_score
from transfer_run import private,audited
from transfer_terminal_wait import wait_terminal
from transfer_audit import evaluate
from recovery_evidence import audit_route
from task2_file_checks import management_tap

SERIAL='emulator-5554'


def run(item,index,out):
    out.mkdir(parents=True,exist_ok=False);skill=item['skill'];initial=[0,40,0,3]
    case_id=fixture(dict(page=skill.get('startPage','overview')),initial)
    previous=private(SERIAL,PROBE,'recorded-workflow-result.json').get('runId')
    library(SERIAL);management_tap('libraryRun'+str(index));snap(SERIAL,out/'review.png');tap(SERIAL,'button1','android')
    result=wait_terminal(lambda:private(SERIAL,PROBE,'recorded-workflow-result.json'),previous,budget_seconds=100)
    if result['traceSha256']!=skill['traceSha256']:raise RuntimeError('WRONG_ORIGINAL_SKILL_EXECUTED')
    finished=time.monotonic();samples=[audited(SERIAL)]
    for delay in (1,5):
        remaining=finished+delay-time.monotonic()
        if remaining>0:time.sleep(remaining)
        samples.append(audited(SERIAL))
    oracle=samples[-1]['oracle']
    raw=adb(SERIAL,'shell','run-as',APP,'cat','shared_prefs/WorkflowActivity.xml')
    persisted=next(n.text for n in ET.fromstring(raw) if n.get('name')=='committed')
    if list(map(int,persisted.split(',')))!=oracle['events'][-1]['saved']:raise RuntimeError('DISK_STATE_DIFFERS')
    journal=[json.loads(line) for line in adb(SERIAL,'shell','run-as',PROBE,'cat','files/workflow-journal-'+result['runId']+'.jsonl').splitlines() if line.strip()]
    judged=evaluate(oracle,result,skill['finalGoals'],samples,case_id=case_id,run_id=result['runId'])
    if skill['version']==3:
        route=process_score(skill,initial,result,oracle,journal)
        if not route['correctCompletion'] or route['falseSuccess']:raise RuntimeError('ORDERED_OLD_PROCESS_DIFFERS')
    else:route=audit_route(result,skill)
    if not judged['actual_success'] or not judged['confirmed_success'] or judged['false_success']:
        raise RuntimeError('LEGACY_REGRESSION_NOT_CORRECT')
    if route.get('valid') is False:raise RuntimeError('LEGACY_ACTION_ORDER_DIFFERS')
    if json.loads(prefs(SERIAL)['approved'])!=skill:raise RuntimeError('ACTIVE_APPROVAL_DIFFERS')
    for name,value in [('item',item),('result',result),('oracle',oracle),('audits',samples),('journal',journal),
                       ('persisted',persisted),('score',dict(judged,route=route,version=skill['version'],
                         steps=len(skill['steps']),normalUi=True,persistedExact=True,modelCalls=0))]:write(out/(name+'.json'),value)
    snap(SERIAL,out/'completed.png')
    print('OLD SKILL PASS '+item['name']+' version='+str(skill['version']),flush=True)
    return dict(name=item['name'],version=skill['version'],steps=len(skill['steps']),
                correctCompletion=True,persistedExact=True,elapsedMs=result['finishedMs']-result['startedMs'])


def main():
    p=argparse.ArgumentParser();p.add_argument('--originals',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    before=json.loads(a.originals.read_text(encoding='utf-8'));original=json.loads(before['library'])
    try:
        if adb(SERIAL,'emu','avd','name').splitlines()[0].strip()!='PortableSkill':raise RuntimeError('WRONG_EMULATOR')
        if not re.search(r'\bversionCode=36\b',adb(SERIAL,'shell','dumpsys','package',PROBE)):raise RuntimeError('WRONG_CANDIDATE')
        approved=json.loads(before['approved']);items=[e for e in original if e['skill']['version']==2][:2]
        items+=[e for e in original if e['skill']==approved]
        if len(items)!=3:raise RuntimeError('ORIGINAL_REGRESSION_SET_NOT_AVAILABLE')
        rows=[]
        for number,item in enumerate(items):
            entries=json.loads(prefs(SERIAL)['library']);indices=[i for i,e in enumerate(entries) if e==item]
            if len(indices)!=1:raise RuntimeError('ORIGINAL_LIBRARY_ENTRY_CHANGED')
            rows.append(run(item,indices[0],a.output/f'old-{number}'));write(a.output/'results.json',rows)
        after=prefs(SERIAL)
        preserved=all(e in json.loads(after['library']) for e in original)
        restored=json.loads(after['approved'])==approved
        write(a.output/'preservation.json',dict(originalLibraryPreserved=preserved,originalActiveApprovalRestored=restored,
              approvedSha256=approved['traceSha256'],oldCount=len(original),newCount=len(json.loads(after['library'])),paidCalls=0))
        if not preserved or not restored:raise RuntimeError('ORIGINAL_STATE_NOT_RESTORED')
    except Exception as error:
        write(a.output/'failure.json',dict(reason=str(error),paidCalls=0))
        try:snap(SERIAL,a.output/'failure.png')
        except Exception:pass
        raise


if __name__=='__main__':main()
