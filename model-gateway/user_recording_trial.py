"""One bounded, user-authorized reuse trial; never writes private approval fields."""
import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path
from workflow_contract import compile_evidence
from workflow_experiment import adb, write
from workflow_capture import PROBE, workbench, click, tree
from transfer_run import approved, run, private, audited
from transfer_terminal_wait import wait_terminal
from teaching_device_check import preferences, screenshot, screen, tap

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/user-recording-100'
ORIGINAL=ROOT/'evaluation/user-skill-60/original'
SERIAL='R5CW134LLBZ'
GOAL=[1,100,1,1]

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def prepare():
    OUT.mkdir(exist_ok=False)
    shutil.copy2(ORIGINAL/'trace-before.json',OUT/'original-trace.json')
    shutil.copy2(ORIGINAL/'workflow-before.json',OUT/'old-skill-backup.json')
    original=json.loads((OUT/'original-trace.json').read_text(encoding='utf-8'))
    assert original['traceId']=='bf28dd49-1566-4819-a98a-b61a5ed8918e'
    assert original['source']=='HUMAN_DECLARED' and original['final']['saved']==GOAL
    confirmed=copy.deepcopy(original)
    confirmed['goal']='打开阅读灯，亮度设为100%，打开风扇并设为低档。'
    assert {k for k in original if original[k]!=confirmed[k]}=={'goal'}
    candidate=compile_evidence(confirmed)
    assert candidate['finalGoals']==GOAL
    write(OUT/'confirmed-trace.json',confirmed)
    write(OUT/'provenance.json',dict(originalSha256=digest(OUT/'original-trace.json'),
        confirmedSha256=digest(OUT/'confirmed-trace.json'),changedFields=['goal'],
        authority='User explicitly confirmed reuse exactly as personally recorded, after brightness discrepancy was explained.',
        originalGoal=original['goal'],confirmedGoal=confirmed['goal'],stepsUnchanged=True,
        source='HUMAN_DECLARED; user reported physical demonstration, not independently proven'))
    cases=[]
    values=[('none',[0,40,0,3]),('partial',[1,100,0,3]),('all',[1,100,1,1])]
    for repeat in range(3):
        for name,initial in values[repeat:]+values[:repeat]:
            cases.append(dict(condition=name,initial=initial,fault='normal',repeat=repeat))
    write(OUT/'protocol.json',dict(goal=GOAL,cases=cases,scope='single S23+; same experimental app; no transfer claim',
        budgetMs=30000,auditAfterSeconds=5,executorChanged=False))
    print('Original preserved; only goal metadata reconciled; nine cases frozen.')

def save():
    skill=json.loads((OUT/'compile/workflow-skill.json').read_text(encoding='utf-8'))
    assert skill==compile_evidence(json.loads((OUT/'confirmed-trace.json').read_text(encoding='utf-8')))
    assert json.loads(preferences('recorded_workflows')['draft'])==skill
    workbench(SERIAL);click(SERIAL,'flowReview')
    ui=tree(SERIAL)
    assert any('Review workflow' in n.get('text','') for n in ui.iter('node'))
    assert any('100%' in n.get('text','') and '[1,100,1,1]' in n.get('text','') for n in ui.iter('node'))
    screenshot(OUT/'review-before-save.png')
    click(SERIAL,'button1','android')
    assert approved(SERIAL)==skill
    write(OUT/'saved-skill.json',skill)
    write(OUT/'save-check.json',dict(saved=True,via='normal UI review confirmation',userAuthorized=True))
    print('SAVED through normal UI; final goals [1,100,1,1].')

def test():
    skill=json.loads((OUT/'saved-skill.json').read_text(encoding='utf-8'))
    assert approved(SERIAL)==skill
    trials=OUT/'trials';trials.mkdir(exist_ok=False)
    protocol=json.loads((OUT/'protocol.json').read_text(encoding='utf-8'))
    rows=[]
    for i,case in enumerate(protocol['cases']):
        folder=trials/f'run-{i:02d}'
        try:row=run(SERIAL,case,folder,skill)
        except Exception as exc:
            write(OUT/'trial-error.json',dict(index=i,error=type(exc).__name__,reason=str(exc)))
            raise
        rows.append(row);write(OUT/'results.json',rows)
        print(json.dumps(dict(index=i,condition=case['condition'],status=row['status'],
            confirmed=row['confirmed_success'],ms=row['elapsed_ms'],inputs=row['inputs'],reason=row['reason'])),flush=True)
    assert approved(SERIAL)==skill
    assert digest(OUT/'original-trace.json')==json.loads((OUT/'provenance.json').read_text(encoding='utf-8'))['originalSha256']
    write(OUT/'summary.json',dict(n=len(rows),confirmed=sum(r['confirmed_success'] for r in rows),
        falseSuccess=sum(r['false_success'] for r in rows),skillUnchanged=True,originalTraceUnchanged=True))
    screen(library=True);screenshot(OUT/'saved-skill-final.png')

def handoff():
    skill=json.loads((OUT/'saved-skill.json').read_text(encoding='utf-8'))
    assert approved(SERIAL)==skill
    old=private(SERIAL,PROBE,'recorded-workflow-result.json')['runId']
    screen(library=True);tap('teachRun')
    screenshot(OUT/'user-run-confirmation.png');click(SERIAL,'button1','android')
    result=wait_terminal(lambda:private(SERIAL,PROBE,'recorded-workflow-result.json'),old)
    assert result['traceId']==skill['traceId'] and result['goal']==GOAL
    assert result['status']=='SUCCEEDED' and len(result['actions'])==0
    actual=audited(SERIAL)
    assert actual['oracle']['events'][-1]['saved']==GOAL
    write(OUT/'user-entry-smoke.json',dict(result=result,audit=actual,passed=True,excludedFromNineTrials=True))
    screen(library=True);tap('teachView');screenshot(OUT/'user-guide-final.png')
    print('User-facing Run entry passed; saved guide left visible.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','save','test','handoff']);a=p.parse_args()
    {'prepare':prepare,'save':save,'test':test,'handoff':handoff}[a.mode]()
