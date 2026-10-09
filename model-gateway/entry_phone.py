"""Actual phone front end: real GPT previews and deliberately delayed real replies.

Delay-only deadline cases are injected, not model-accuracy samples. No approval,
target task input, credential persistence or user-skill editing is allowed here.
"""
import argparse
import json
import os
from pathlib import Path
import re
import threading
import time
from compiler import ModelError
from deadline_remote import gpt_remote
from intent_bridge import BridgeServer
from skill_selection import select_skill
from named_journey_device import prefs,library,home,tap,text,snap,PROBE,APP
from workflow_capture import tree
from workflow_experiment import adb,write
from transfer_run import private

def reverse_target(serial):
    return next((v.split()[-1] for v in adb(serial,'reverse','--list').splitlines()
                 if len(v.split())>=3 and v.split()[-2]=='tcp:8765'),None)

def restore_input(serial,saved):
    library(serial);text(serial,'libraryInput',saved)
    values=[n.get('text','') for n in tree(serial).iter('node')
            if n.get('resource-id')==PROBE+':id/libraryInput']
    home(serial)
    if saved=='':
        stored=prefs(serial,'WorkflowLibraryActivity')
        return 'text' in stored and stored['text'] in ('',None)
    return values==[saved]


def read_input(serial):
    # Persist through the ordinary lifecycle. An empty EditText can expose its
    # hint as accessibility text, so hints are never backed up as user content.
    library(serial);home(serial)
    stored=prefs(serial,'WorkflowLibraryActivity')
    if 'text' not in stored:raise RuntimeError('INPUT_SNAPSHOT_MISSING')
    library(serial)
    return stored['text'] or ''

def run(out,injected=False,saturated_cancellations=False):
    if saturated_cancellations and not injected:raise ValueError('SATURATION_REQUIRES_INJECTED_MODE')
    out.mkdir(parents=True,exist_ok=False);serial='R5CW134LLBZ'
    if not injected:
        from win_credentials import read_key
        os.environ['OPENAI_API_KEY']=read_key()
    before=prefs(serial);oracle=private(serial,APP,'workflow-oracle.json');token=prefs(serial,'language_connection')['pairing']
    prior=reverse_target(serial)
    if prior and not re.fullmatch(r'tcp:\d+',prior):raise ValueError('INVALID_REVERSE')
    library(serial);saved=next(n.get('text','') for n in tree(serial).iter('node') if n.get('resource-id')==PROBE+':id/libraryInput')
    write(out/'input-before.json',dict(text=saved))
    release=threading.Event();ready=threading.Event();finished=threading.Event();entered=threading.Event()
    current={};remote_count=[0];rows=[]
    def select(command,skills,budget):
        case=current.copy();entered.set()
        def transport(body,timeout):
            if case['scenario']=='deadline':
                ready.set();release.wait(20);finished.set()
                return dict(draft=dict(status='invoke',skill_id=skills[0]['id'],message='Injected late proposal'))
            write(case['folder']/'request.json',body)
            if injected:
                selected=next(s for s in skills if s['finalGoals']==[1,60,1,1])
                response=dict(draft=dict(status='invoke',skill_id=selected['id'],message='Injected preview; not a model result.'))
            else:
                if remote_count[0]>=10:raise ModelError('PER_REQUEST_CAP')
                remote_count[0]+=1;response=gpt_remote(body,timeout)
            write(case['folder']/'response.json',response);ready.set()
            if case['scenario']!='normal':release.wait(20)
            finished.set();return response
        return select_skill(command,skills,lambda body:budget.call(transport,body,'INJECTED' if injected or case['scenario']=='deadline' else 'GPT'))
    server=BridgeServer(('127.0.0.1',0),token,max_calls=14,bounded_selector=select)
    if saturated_cancellations:
        # Fill only unknown early-cancellation storage. Current requests must
        # still be revocable using their existing bounded event entries.
        server.cancelled_ids.update(f'{i:032x}' for i in range(server.max_calls))
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    write(out/'protocol.json',dict(remoteCallCap=10,repeats=2,normalLanguages=['zh','en'],
        realModelScenarios=['normal','cancel','edit','leave'],injectedScenarios=['deadline'],
        safetyRepliesHaveControlledDeliveryDelay=True,targetInputsPermitted=0,approvalChangesPermitted=0,allRepliesInjected=injected,
        unknownCancellationStorageSaturated=saturated_cancellations))
    try:
        adb(serial,'reverse','tcp:8765','tcp:'+str(server.server_port))
        cases=[dict(scenario='normal',language=lang,repeat=rep) for rep in range(2) for lang in ['zh','en']]+\
            [dict(scenario=scenario,language='en',repeat=rep) for rep in range(2) for scenario in ['cancel','edit','leave','deadline']]
        for i,case in enumerate(cases):
            folder=out/f'{i:02d}-{case["scenario"]}';folder.mkdir();case['folder']=folder;current.clear();current.update(case)
            release.clear();ready.clear();finished.clear();entered.clear()
            library(serial);command='请执行我保存的阅读60技能。' if case['language']=='zh' else 'Please run my saved Reading60 workflow.'
            text(serial,'libraryInput',command);before_ids=set(server.selection_events)
            tap(serial,'libraryChoose');assert entered.wait(5),'request never arrived'
            assert ready.wait(7),'no model reply / injected ready signal'
            if case['scenario']=='normal':
                ui=tree(serial);labels=[n.get('text','') for n in ui.iter('node')]
                assert any('Reading60' in value and ('Confirm' in value or '确认' in value) for value in labels),'wrong/missing confirmation'
                assert any(n.get('resource-id')=='android:id/button1' for n in ui.iter('node'))
                snap(serial,folder/'preview.png');tap(serial,'button2','android')
            else:
                if case['scenario']=='cancel':tap(serial,'libraryCancel')
                elif case['scenario']=='edit':text(serial,'libraryInput','Do not run anything; this request is cancelled.')
                elif case['scenario']=='leave':home(serial)
                else:
                    # Wait for the real product 8-second server budget, not a shorter test budget.
                    end=time.monotonic()+10
                    while time.monotonic()<end and not server.selection_audit:time.sleep(.05)
                    time.sleep(9 if len(server.selection_audit)<i+1 else .2)
                release.set();assert finished.wait(4),'worker not released';time.sleep(.25)
                ui=tree(serial)
                assert not any(n.get('resource-id')=='android:id/button1' for n in ui.iter('node')),'late confirmation'
                snap(serial,folder/'terminal.png')
            after=prefs(serial)
            assert after['library']==before['library'] and after.get('approved')==before.get('approved')
            assert after.get('result')==before.get('result') and private(serial,APP,'workflow-oracle.json')==oracle
            ids=set(server.selection_events)-before_ids;assert len(ids)==1,'request identity audit'
            identity=next(iter(ids));audits=[r for r in server.selection_audit if r['request_id']==identity]
            assert len(audits)==1,'missing terminal audit'
            if case['scenario'] in ['cancel','edit','leave']:
                assert identity in server.cancelled_ids or server.selection_events[identity].is_set(),'phone did not send cancellation RPC'
            if case['scenario']=='deadline':assert audits[0]['outcome']=='SELECTION_DEADLINE'
            row={k:v for k,v in case.items() if k!='folder'}
            row.update(status='PASS',requestId=identity,audit=audits[0],targetStateUnchanged=True,
                catalogueUnchanged=True,approvalUnchanged=True,controlledDeliveryDelay=case['scenario'] in ['cancel','edit','leave'],
                realModel=not injected and case['scenario']!='deadline',remoteCallsSoFar=remote_count[0],
                unknownCancellationIds=len(server.cancelled_ids),knownRequestRecords=len(server.selection_events))
            rows.append(row);write(folder/'row.json',row);write(out/'results.json',rows)
            print('PASS phone '+case['scenario']+' '+case['language']+' '+str(case['repeat']),flush=True)
    except Exception as error:
        write(out/'failure.json',dict(type=type(error).__name__,reason=str(error)));raise
    finally:
        release.set();server.shutdown();server.server_close();worker.join(3)
        if prior:adb(serial,'reverse','tcp:8765',prior)
        else:adb(serial,'reverse','--remove','tcp:8765')
        input_restored=restore_input(serial,saved)
        reverse_restored=reverse_target(serial)==prior
        after=prefs(serial)
        restored=dict(reverseRestored=reverse_restored,inputRestored=input_restored,libraryUnchanged=after['library']==before['library'],
            approvedUnchanged=after.get('approved')==before.get('approved'),resultUnchanged=after.get('result')==before.get('result'),
            oracleUnchanged=private(serial,APP,'workflow-oracle.json')==oracle,remoteCalls=remote_count[0])
        write(out/'restored.json',restored)
        if not all(value for key,value in restored.items() if key!='remoteCalls'):
            raise RuntimeError('RESTORATION_NOT_VERIFIED')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--injected',action='store_true');p.add_argument('--saturated-cancellations',action='store_true');a=p.parse_args();run(a.output,a.injected,a.saturated_cancellations)
