"""Small paired real-phone chain check. Normal preview/confirm UI, fixed skills."""
import argparse
import json
import os
import random
import re
import threading
from pathlib import Path
from intent_bridge import BridgeServer
from jev_selection_benchmark import call
from named_journey_device import home,tap,text,prefs,fixture,library,PROBE,APP
from workflow_capture import tree
from partial_journey import run
from transfer_run import private
from transfer_terminal_wait import wait_terminal
from workflow_experiment import adb,write
from win_credentials import read_key

CASES=[
 dict(skill='lamp',condition='none',repeat=0,initial=[0,40,1,3],text='Turn on only the reading lamp at sixty percent. Keep the fan unchanged.'),
 dict(skill='lamp',condition='parameter',repeat=0,initial=[1,40,0,2],text='只打开阅读灯，亮度设为60%，不要改变风扇。'),
 dict(skill='lamp',condition='all',repeat=0,initial=[1,60,1,3],text='Please run LampOnly60.'),
 dict(skill='fan',condition='none',repeat=0,initial=[1,80,0,3],text='只打开风扇并设为低档，阅读灯保持不变。'),
 dict(skill='fan',condition='parameter',repeat=0,initial=[0,40,1,3],text='Turn on only the fan at low speed. Keep the reading lamp unchanged.'),
 dict(skill='fan',condition='all',repeat=0,initial=[1,100,1,1],text='执行我保存的只风扇低档技能。')]

def selection_call(backend,text_value,skills):
    if backend=='jev':return call(backend,text_value,skills)
    from model_coordination import measure
    from start_teaching_bridge import resolve_selector
    row=measure('F' if backend=='routed-full' else 'R' if backend=='routed' else 'G',text_value,skills,
        selector=resolve_selector('routed') if backend=='routed-full' else None)
    row.update(backend=backend,metadata=dict(model=row.get('model','literal-name' if row['route']=='literal-name' else 'unavailable')))
    return row

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--guard',action='store_true');p.add_argument('--candidate',choices=['jev','routed','routed-full'],default='jev');a=p.parse_args();out=a.output;out.mkdir(parents=True,exist_ok=False)
    serial='R5CW134LLBZ';state=prefs(serial);old=private(serial,APP,'workflow-oracle.json');saved=old['events'][-1]['saved'] if old.get('events') else old['initial']
    token=prefs(serial,'language_connection')['pairing'];os.environ['OPENAI_API_KEY']=read_key()
    reverse=adb(serial,'reverse','--list');previous=next((s.split()[-1] for s in reverse.splitlines() if len(s.split())>=3 and s.split()[-2]=='tcp:8765'),None)
    if previous and not re.fullmatch(r'tcp:\d+',previous):raise ValueError('Unexpected reverse configuration')
    library(serial);original_input=next(n.get('text','') for n in tree(serial).iter('node') if n.get('resource-id')==PROBE+':id/libraryInput');home(serial)
    models=[];backend=['gpt']
    def selector(text_value,skills):
        if a.guard and backend[0]=='jev':
            from jev_guard_confirmation import guarded_call
            r=guarded_call(text_value,skills)
        else:r=selection_call(backend[0],text_value,skills)
        models.append(r);write(out/'model-calls.json',models)
        if not r['available']:raise RuntimeError('MODEL_UNAVAILABLE')
        return r['selection']
    server=BridgeServer(('127.0.0.1',0),token,max_calls=24,skill_selector=selector)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();adb(serial,'reverse','tcp:8765','tcp:'+str(server.server_port))
    trials=[];rng=random.Random(4810)
    for i,c in enumerate(CASES):
        order=['gpt',a.candidate];rng.shuffle(order)
        for b in order:trials.append(dict(index=i,backend=b,case=c))
    import hashlib
    write(out/'protocol.json',dict(trials=trials,negativeTexts=['执行阅读60，但亮度改为20%。','Do not run LampOnly60.'],languageAndExecutorTimesSeparate=True,budgetMs=30000,postAuditSeconds=5,maxCalls=24,jevGuard=a.guard,candidate=a.candidate,
        sourceHashes={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in ['phone_jev_ab.py','model_coordination.py','selection_routing.py','skill_selection.py','jev_selection.py']}))
    rows=[]
    try:
        for trial in trials:
            backend[0]=trial['backend'];before_calls=len(models)
            folder=out/(str(trial['index'])+'-'+backend[0])
            score=run(serial,trial['case'],folder,trial['case']['text'])
            assert len(models)==before_calls+1 and models[-1]['backend']==backend[0]
            score.update(backend=backend[0],selectionMs=models[-1]['ms'],returnedModel=models[-1]['metadata']['model'],coreStageSumMs=models[-1]['ms']+score['elapsed_ms'],remoteCalls=models[-1].get('remoteCalls',1))
            rows.append(score);write(out/'results.json',rows)
            print(json.dumps(dict(backend=backend[0],index=trial['index'],actual=score['actual_success'],status=score['status'],selectionMs=score['selectionMs'],executionMs=score['elapsed_ms'],unexpected=score['unexpectedInputs'],nonTargetViolation=score['non_target_violation'])),flush=True)
        negative=[]
        for b in ('gpt',a.candidate):
            backend[0]=b
            for command in ['执行阅读60，但亮度改为20%。','Do not run LampOnly60.']:
                before=prefs(serial);observed=private(serial,APP,'workflow-oracle.json');library(serial);text(serial,'libraryInput',command)
                count=len(models);tap(serial,'libraryChoose')
                import time
                deadline=time.monotonic()+55
                while len(models)==count and time.monotonic()<deadline:time.sleep(.2)
                assert len(models)==count+1 and models[-1]['available'];time.sleep(.7)
                assert models[-1]['selection']['status'] in ('clarify','reject')
                assert not any(n.get('resource-id')=='android:id/button1' for n in tree(serial).iter('node'))
                assert prefs(serial).get('result')==before.get('result') and private(serial,APP,'workflow-oracle.json')==observed
                negative.append(dict(backend=b,text=command,noInvocation=True,noFixtureChange=True));write(out/'negative-checks.json',negative)
        print('PASS 12 paired phone executions and 4 no-invocation checks',flush=True)
    finally:
        server.shutdown();server.server_close();thread.join(timeout=3)
        if previous:adb(serial,'reverse','tcp:8765',previous)
        else:adb(serial,'reverse','--remove','tcp:8765')
        items=json.loads(state['library']);old_approved=state.get('approved');match=[i for i,e in enumerate(items) if e['skill']==json.loads(old_approved or '{}')]
        if len(match)==1 and prefs(serial).get('approved')!=old_approved:
            fixture(serial,saved);r=prefs(serial).get('result');old_id=json.loads(r)['runId'] if r and r.startswith('{') else None
            library(serial);tap(serial,'libraryRun'+str(match[0]));tap(serial,'button1','android');wait_terminal(lambda:private(serial,PROBE,'recorded-workflow-result.json'),old_id)
        fixture(serial,saved)
        library(serial);text(serial,'libraryInput',original_input or ' ')
        home(serial);write(out/'restored.json',dict(catalogueUnchanged=prefs(serial)['library']==state['library'],selectionRestored=prefs(serial).get('approved')==old_approved,reverseRestored=True,fixtureRestored=private(serial,APP,'workflow-oracle.json')['initial']==saved))

if __name__=='__main__':main()
