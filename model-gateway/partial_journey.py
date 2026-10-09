"""Controlled four-step user journey; no private approvals are written by this operator."""
import argparse
import json
import random
import time
from pathlib import Path
from named_journey_device import prefs,fixture,home,library,tap,text,snap,PROBE,APP
from workflow_experiment import adb,write
from workflow_contract import compile_evidence
from transfer_run import approved,private,audited
from transfer_terminal_wait import wait_terminal
from transfer_audit import evaluate
from recovery_evidence import audit_route

SKILLS={
 'lamp':dict(name='只灯60 / LampOnly60',goal='Turn on the lamp at 60 percent. Keep the fan unchanged.',initial=[0,40,0,3],target=[1,60,None,None],group='Lamp'),
 'fan':dict(name='只风扇低档 / FanOnlyLow',goal='Turn on the fan at low speed. Keep the lamp unchanged.',initial=[0,40,0,3],target=[None,None,1,1],group='Fan')}

def capture(serial,key,out):
    spec=SKILLS[key];out.mkdir(parents=True,exist_ok=False);write(out/'protocol.json',dict(spec,source='AUTOMATED'))
    old=approved(serial);write(out/'approval-before.json',old);write(out/'before.json',fixture(serial,spec['initial']))
    home(serial);tap(serial,'homeAdvanced');tap(serial,'guidedTest')
    if prefs(serial,'teaching_journey').get('currentTrace'):tap(serial,'teachNew')
    text(serial,'teachName',spec['name']);text(serial,'teachGoal',spec['goal']);tap(serial,'teachRecord');tap(serial,'button1','android');time.sleep(1)
    group=spec['group'];value=60 if key=='lamp' else 1
    for control in ['wfOpen'+group,'wf'+group+'Power','wf'+group+'Value'+str(value),'wf'+group+'Save']:tap(serial,control,APP)
    snap(serial,out/'four-step-hint.png');home(serial);tap(serial,'teachEntry');tap(serial,'teachStop')
    trace=private(serial,PROBE,'workflow-trace.json');write(out/'trace.json',trace)
    candidate=compile_evidence(trace);write(out/'local-candidate.json',candidate)
    assert trace['source']=='AUTOMATED' and candidate['finalGoals']==spec['target'] and approved(serial)==old
    write(out/'oracle.json',audited(serial));snap(serial,out/'record-preview.png')
    print('CAPTURED '+key+' four steps; old approval unchanged',flush=True)

def save(serial,key,out):
    trace=json.loads((out/'trace.json').read_text(encoding='utf-8'));assert private(serial,PROBE,'workflow-trace.json')==trace
    tap(serial,'teachGenerate')
    for _ in range(55):
        state=prefs(serial,'teaching_journey')
        if state.get('draft') and state.get('draftTrace') and json.loads(state['draftTrace'])==trace:break
        time.sleep(1)
    else:raise RuntimeError('No reviewed draft; evidence kept')
    skill=json.loads(state['draft']);assert skill==compile_evidence(trace);write(out/'model-candidate.json',skill)
    snap(serial,out/'guide.png');tap(serial,'teachSave');snap(serial,out/'save-dialog.png');tap(serial,'button1','android')
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        p=prefs(serial)
        if json.loads(p['approved'])==skill:break
        time.sleep(.2)
    assert json.loads(p['approved'])==skill
    pack=next(e for e in json.loads(p['library']) if e['skill']==skill);assert pack['name']==SKILLS[key]['name']
    write(out/'saved-skill.json',skill);write(out/(key+'-partial.json'),pack);write(out/'library-after.json',json.loads(p['library']));snap(serial,out/'saved.png')
    print('SAVED '+key+' through reviewed normal UI',flush=True)

def cases():
    rows=[]
    for repeat in range(2):
        block=[]
        for key in SKILLS:
            for condition in ['none','parameter','all']:
                if key=='lamp':initial=[0 if condition=='none' else 1,60 if condition=='all' else 40,repeat,1+repeat]
                else:initial=[repeat,60+20*repeat,0 if condition=='none' else 1,1 if condition=='all' else 3]
                block.append(dict(skill=key,condition=condition,repeat=repeat,initial=initial))
        random.Random(2400+repeat).shuffle(block);rows+=block
    return rows

def entry(serial,key):
    items=json.loads(prefs(serial)['library']);found=[(i,e) for i,e in enumerate(items) if e['skill']['finalGoals']==SKILLS[key]['target']]
    if len(found)!=1:raise RuntimeError('Missing/ambiguous partial skill')
    return found[0]

def score_case(case,skill,oracle,result,samples,journal,before):
    goals=skill['finalGoals'];resolved=[a if g is None else g for a,g in zip(case['initial'],goals)]
    assert oracle['initial']==case['initial'] and result['traceSha256']==skill['traceSha256']
    assert result['requestedGoals']==goals and result['goal']==resolved
    bound=[e for e in journal if e['kind']=='GOALS_BOUND'];assert len(bound)==1 and bound[0]['data']['resolved']==resolved and bound[0]['data']['initial']==case['initial']
    row=evaluate(oracle,result,goals,samples,case_id=before['caseId'],run_id=result['runId'])
    changes=sum(g is not None and g!=a for a,g in zip(case['initial'],goals));expected=2+changes if changes else 0
    inputs=[e for e in oracle['events'] if e['ms']>=result['startedMs'] and e['kind'].startswith(('input:','edit:'))]
    allowed={s['id'] for s in skill['steps']}
    row.update(case=case,reason=result['reason'],route=audit_route(result,skill),expectedInputs=expected,
        oracleInputs=len(inputs),unexpectedInputs=sum(e['kind'].split(':',1)[1] not in allowed for e in inputs),
        afterDeadlineInputs=sum(e['ms']>=result['deadlineMs'] for e in inputs),extraInputs=max(0,len(inputs)-expected))
    return row

def run(serial,case,out,language=None):
    out.mkdir(parents=True,exist_ok=False);index,item=entry(serial,case['skill']);skill=item['skill'];write(out/'skill.json',skill);write(out/'case.json',case)
    if case.get('fault','normal')!='normal':
        import secrets
        case_id=secrets.token_hex(8)
        adb(serial,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','caseId',case_id,'--es','layout','multi','--es','fault',case['fault'],'--es','initial',','.join(map(str,case['initial'])))
        before=private(serial,APP,'workflow-oracle.json');assert before['caseId']==case_id and before['fault']==case['fault'] and before['initial']==case['initial']
    else:before=fixture(serial,case['initial'])
    write(out/'before.json',before);p=prefs(serial).get('result');old=json.loads(p)['runId'] if p and p.startswith('{') else None
    library(serial)
    if language:
        from workflow_capture import tree
        text(serial,'libraryInput',language);tap(serial,'libraryChoose')
        for _ in range(55):
            ui=tree(serial)
            if any(n.get('resource-id')=='android:id/button1' for n in ui.iter('node')):break
            time.sleep(.4)
        else:raise RuntimeError('No language confirmation')
        assert any(item['name'] in n.get('text','') for n in ui.iter('node'));write(out/'language.json',dict(text=language,selectedName=item['name']))
    else:tap(serial,'libraryRun'+str(index))
    snap(serial,out/'confirmation.png');tap(serial,'button1','android')
    result=wait_terminal(lambda:private(serial,PROBE,'recorded-workflow-result.json',timeout=3),old);write(out/'terminal.json',result)
    finished=time.monotonic();samples=[audited(serial)]
    for delay in (1,5):
        left=finished+delay-time.monotonic()
        if left>0:time.sleep(left)
        samples.append(audited(serial))
    oracle=samples[-1]['oracle'];write(out/'audit.json',samples);write(out/'oracle.json',oracle)
    journal=[json.loads(line) for line in adb(serial,'shell','run-as',PROBE,'cat','files/workflow-journal-'+result['runId']+'.jsonl').splitlines() if line.strip()];write(out/'journal.json',journal)
    row=score_case(case,skill,oracle,result,samples,journal,before);write(out/'score.json',row);snap(serial,out/'result.png');return row

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['capture','save','freeze','run','smoke']);p.add_argument('--device',default='R5CW134LLBZ');p.add_argument('--key',choices=SKILLS,default='lamp');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='freeze':a.output.mkdir(parents=True,exist_ok=False);write(a.output/'protocol.json',dict(cases=cases(),device=a.device,budgetMs=30000,postAuditSeconds=5));return
    if a.mode in ('capture','save'):
        try:globals()[a.mode](a.device,a.key,a.output)
        except Exception as e:write(a.output/(a.mode+'-failure.json'),dict(error=type(e).__name__,reason=str(e)));raise
        return
    if a.mode=='smoke':print(json.dumps(run(a.device,cases()[0],a.output)));return
    rows=[];protocol=json.loads((a.output/'protocol.json').read_text(encoding='utf-8'))
    for i,case in enumerate(protocol['cases']):
        try:
            row=run(a.device,case,a.output/f'run-{i:03d}');rows.append(row);write(a.output/'results.json',rows)
            print(json.dumps(dict(index=i,skill=case['skill'],condition=case['condition'],actual=row['actual_success'],status=row['status'],nonTargetViolation=row['non_target_violation'],ms=row['elapsed_ms'])),flush=True)
        except Exception as e:write(a.output/'infrastructure-error.json',dict(index=i,error=type(e).__name__,reason=str(e)));raise

if __name__=='__main__':main()
