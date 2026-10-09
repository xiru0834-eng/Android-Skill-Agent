"""Execute named skills through library preview and confirmation, audited separately."""
import argparse
import json
import random
import time
from pathlib import Path
from named_journey_device import prefs,fixture,library,tap,snap,DEMONSTRATIONS,PROBE,APP
from workflow_experiment import adb,write
from transfer_run import private,audited
from transfer_audit import evaluate
from transfer_terminal_wait import wait_terminal
from recovery_evidence import audit_route
from startup_audit import input_safety
from migration_matrix import display
from user_robustness import restore_display

def cases(emulator):
    rng=random.Random(291117);rows=[]
    for block in (['reference','compact'] if emulator else ['phone-1','phone-2']):
        part=[]
        for key,c in DEMONSTRATIONS.items():
            for condition,initial in [('none',c['initial']),('partial',c['target'][:2]+c['initial'][2:]),('all',c['target'])]:
                part.append(dict(skill=key,condition=condition,initial=initial,config=block,fault='normal'))
        rng.shuffle(part);rows.extend(part)
    return rows

def entry(serial,key):
    target=DEMONSTRATIONS[key]['target'];entries=json.loads(prefs(serial)['library'])
    matches=[(i,e) for i,e in enumerate(entries) if e['skill']['finalGoals']==target]
    if len(matches)!=1:raise RuntimeError('Missing or ambiguous reviewed target')
    return matches[0]

def run(serial,case,out,language=None):
    out.mkdir(parents=True,exist_ok=False);index,item=entry(serial,case['skill']);skill=item['skill']
    write(out/'skill.json',skill);write(out/'case.json',case)
    before=fixture(serial,case['initial']);write(out/'before.json',before)
    previous=prefs(serial).get('result');old=json.loads(previous)['runId'] if previous and previous.startswith('{') else None
    library(serial);start=time.monotonic()
    if language:
        from named_journey_device import text,node
        text(serial,'libraryInput',language);tap(serial,'libraryChoose')
        for _ in range(55):
            from workflow_capture import tree
            ui=tree(serial)
            if any(n.get('resource-id')=='android:id/button1' for n in ui.iter('node')):break
            time.sleep(.4)
        else:raise RuntimeError('No language confirmation')
        assert any(item['name'] in n.get('text','') for n in ui.iter('node'))
    else:tap(serial,'libraryRun'+str(index))
    snap(serial,out/'confirmation.png');tap(serial,'button1','android')
    result=wait_terminal(lambda:private(serial,PROBE,'recorded-workflow-result.json',timeout=3),old)
    ui_ms=round((time.monotonic()-start)*1000);finished=time.monotonic();write(out/'terminal.json',result)
    assert result['traceSha256']==skill['traceSha256'] and result['traceId']==skill['traceId'] and result['goal']==skill['finalGoals']
    samples=[audited(serial)]
    for delay in (1,5):
        left=finished+delay-time.monotonic()
        if left>0:time.sleep(left)
        samples.append(audited(serial))
    oracle=samples[-1]['oracle'];write(out/'audit.json',samples);write(out/'oracle.json',oracle)
    import xml.etree.ElementTree as ET
    state=ET.fromstring(adb(serial,'shell','run-as',APP,'cat','shared_prefs/WorkflowActivity.xml'))
    persisted=next(n.text for n in state if n.get('name')=='committed');write(out/'persisted.json',persisted)
    assert list(map(int,persisted.split(',')))==oracle['events'][-1]['saved']
    journal=[json.loads(line) for line in adb(serial,'shell','run-as',PROBE,'cat','files/workflow-journal-'+result['runId']+'.jsonl').splitlines() if line.strip()]
    write(out/'journal.json',journal)
    row=evaluate(oracle,result,skill['finalGoals'],samples,case_id=before['caseId'],run_id=result['runId'])
    row.update(case=case,ui_completion_ms=ui_ms,reason=result['reason'],route=audit_route(result,skill),inputSafety=input_safety(oracle,result,skill),entry='named-library',language=language)
    write(out/'score.json',row);snap(serial,out/'result.png');return row

def main():
    p=argparse.ArgumentParser();p.add_argument('--device',choices=['R5CW134LLBZ','emulator-5554'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--freeze',action='store_true');p.add_argument('--smoke',action='store_true');a=p.parse_args()
    if a.freeze:
        a.output.mkdir(parents=True,exist_ok=False);write(a.output/'protocol.json',dict(cases=cases(a.device=='emulator-5554'),device=a.device,budgetMs=30000,postAuditSeconds=5));return
    if a.smoke:
        row=run(a.device,dict(skill='reading',condition='none',initial=[0,40,0,3],fault='normal'),a.output)
        print(json.dumps(row));return
    protocol=json.loads((a.output/'protocol.json').read_text(encoding='utf-8'));original=display(a.device);write(a.output/'display-before.json',original);rows=[]
    try:
        previous=None
        for index,case in enumerate(protocol['cases']):
            if a.device=='emulator-5554' and previous!=case['config']:
                size,dpi=('1080x2400','420') if case['config']=='reference' else ('720x1280','420')
                adb(a.device,'shell','wm','size',size);adb(a.device,'shell','wm','density',dpi);time.sleep(1)
                write(a.output/(case['config']+'-display.json'),display(a.device));previous=case['config']
            try:row=run(a.device,case,a.output/f'run-{index:03d}')
            except Exception as e:
                write(a.output/'infrastructure-error.json',dict(index=index,error=type(e).__name__,reason=str(e)));raise
            rows.append(row);write(a.output/'results.json',rows)
            print(json.dumps(dict(index=index,skill=case['skill'],condition=case['condition'],status=row['status'],actual=row['actual_success'],ms=row['elapsed_ms'])),flush=True)
    finally:
        if a.device=='emulator-5554':restore_display(a.device,original)
        write(a.output/'summary.json',dict(planned=len(protocol['cases']),scored=len(rows),unscored=len(protocol['cases'])-len(rows),
            actual=sum(r['actual_success'] for r in rows),confirmed=sum(r['confirmed_success'] for r in rows),falseSuccess=sum(r['false_success'] for r in rows)))

if __name__=='__main__':main()
