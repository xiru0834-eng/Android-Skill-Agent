"""Evaluator-only real read-only/safety checks; never reset a dirty phone session."""
import argparse
import json
import time
from pathlib import Path
from android_bridge import AndroidBridge
from evaluation_device import adb,read_business,state,check_clean,prepare
from navigation_controller import observe,candidate
from native_materials import validate_native_observation,native_bundle
from bundle_store import BundleStore
from bundle_contract import need

BASE=Path(__file__).resolve().parent
PHONE='R5CW134LLBZ';PAD='emulator-5556'

def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def phone_checks(folder):
    serial=PHONE;folder.mkdir(parents=True,exist_ok=False)
    before=read_business(serial);need(before is not None,'PHONE_LIVE_STATE_UNAVAILABLE')
    write(folder/'evaluator-before.json',before);rows=[];bundles=[];bridge=None
    try:
        for label,pkg,activity,ui in [('EXISTING_DRAFT','edu.sydney.transferlab','WorkflowActivity','native-single-v6'),
                                      ('PARAMETERROOM','edu.sydney.parameterroom','ParameterRoomActivity','native-v6')]:
            # No initial/caseId/layout: audited normal resume path, not a reset/preparer.
            adb(serial,'shell','am','start','-n',pkg+'/.'+activity)
            if pkg=='edu.sydney.transferlab':
                now=read_business(serial)
                need(now['caseId']==before['caseId'] and state(now)==state(before),'PHONE_DRAFT_CHANGED_ON_RESUME')
            bridge=AndroidBridge(serial);need(bridge.start(pkg)['status']=='STARTED','SCOPE_START_FAILED')
            observations=[]
            for repeat in range(1,4):
                o=observe(bridge);validate_native_observation(o);observations.append(o)
                rows.append({'condition':label,'repeat':repeat,'status':'PASS','observation_id':o['observation_id'],
                    'node_count':len(o['tree']['nodes']),'input_calls':0,'screenshot':'NOT_REQUESTED'})
            env={'app_package':pkg,'app_build':'6','environment_id':'existing-workflow-lab' if pkg=='edu.sydney.transferlab' else 'existing-parameter-room',
                 'ui_revision':ui,'domain':'EXPERIMENT_APP'}
            b=native_bundle(observations,[],env);bundles.append(b);write(folder/(label+'-bundle.json'),b)
            if pkg=='edu.sydney.transferlab':
                need(len(b['pages'])==1 and b['pages'][0]['identity_status']=='KNOWN' and len(b['pages'][0]['entities'])==2,'PHONE_PAGE_IDENTITY_INCOMPLETE')
            write(folder/(label+'-observations.json'),observations)
            need(bridge.stop()['status']=='STOPPED','SCOPE_STOP_FAILED');write(folder/(label+'-receipts.json'),bridge.calls);bridge=None
        after=read_business(serial);write(folder/'evaluator-after.json',after)
        need(after['caseId']==before['caseId'] and state(after)==state(before),'PHONE_USER_WORK_CHANGED')
        with BundleStore(folder/'phone-memory.sqlite',create=True) as store:
            for i,b in enumerate(bundles):store.append(b,expected_revision=i)
        summary={'status':'PASS','read_observations':len(rows),'cases':rows,'input_calls':0,
                 'phone_case_id_preserved':after['caseId']==before['caseId'],'phone_saved_and_draft_preserved':state(after)==state(before),
                 'positive_navigation':'NOT_TESTED_EXISTING_UNSAVED_DRAFT','model_calls':0}
    except Exception as e:
        summary={'status':'FAILED','error':type(e).__name__+':'+str(e),'cases':rows}
    finally:
        if bridge:
            try:bridge.cancel()
            except Exception:pass
            write(folder/'failure-receipts.json',bridge.calls)
        # Restore the original foreground without passing reset parameters.
        try:adb(serial,'shell','am','start','-n','edu.sydney.parameterroom/.ParameterRoomActivity')
        except Exception as e:summary['restore_foreground_error']=str(e);summary['status']='FAILED'
    write(folder/'summary.json',summary);print(json.dumps({'phone':summary},ensure_ascii=False),flush=True)
    return summary

def safety_checks(folder):
    folder.mkdir(parents=True,exist_ok=False);serial=PAD;prior=read_business(serial);check_clean(prior)
    rows=[];bridge=None
    try:
        # 1: Current real business control in existing ParameterRoom, never authorized for navigation.
        adb(serial,'shell','am','start','-n','edu.sydney.parameterroom/.ParameterRoomActivity')
        bridge=AndroidBridge(serial);need(bridge.start('edu.sydney.parameterroom')['status']=='STARTED','SCOPE_START_FAILED')
        o=observe(bridge);candidates=[n for n in o['tree']['nodes'] if n['visible'] and n['role'] in {'slider','switch'}]
        need(bool(candidates),'REAL_BUSINESS_CANDIDATE_UNAVAILABLE')
        r=bridge.click(o,candidates[0]);rows.append({'condition':'unsafe_business_candidate','receipt':r,'expected':'UNAUTHORIZED_ACTION'})
        bridge.stop();write(folder/'business-receipts.json',bridge.calls);bridge=None

        saved=state(prior)['saved'] if prior else [0,40,0,3]
        prepare(serial,saved,layout='multi');initial=read_business(serial);check_clean(initial)
        write(folder/'evaluator-before.json',initial)
        # 2/3/4/5 use the same real clean public navigation candidate and distinct bounded scopes.
        bridge=AndroidBridge(serial);need(bridge.start('edu.sydney.transferlab')['status']=='STARTED','SCOPE_START_FAILED')
        old=observe(bridge);node=candidate(old,'Reading lamp')
        observe(bridge);r=bridge.click(old,node);rows.append({'condition':'stale_observation','receipt':r,'expected':'STALE_OBSERVATION'})
        fresh=observe(bridge);node=candidate(fresh,'Reading lamp')
        bridge.cancel();r=bridge.click(fresh,node);rows.append({'condition':'cancel_then_click','receipt':r,'expected':'CANCELLED'})
        write(folder/'stale-cancel-receipts.json',bridge.calls);bridge=None

        bridge=AndroidBridge(serial);need(bridge.start('edu.sydney.parameterroom')['status']=='STARTED','SCOPE_START_FAILED')
        r=bridge.observe();rows.append({'condition':'window_mismatch','receipt':r,'expected':'WINDOW_MISMATCH'})
        bridge.cancel();write(folder/'window-receipts.json',bridge.calls);bridge=None

        bridge=AndroidBridge(serial);need(bridge.start('edu.sydney.transferlab')['status']=='STARTED','SCOPE_START_FAILED')
        # Do not replace the bridge's active nonce when testing a second start.
        import uuid
        r=bridge.request('start',scope_id=uuid.uuid4().hex,app_package='edu.sydney.transferlab')
        rows.append({'condition':'scope_already_active','receipt':r,'expected':'SCOPE_ALREADY_ACTIVE'})
        bridge.stop();write(folder/'active-scope-receipts.json',bridge.calls);bridge=None
        after=read_business(serial);write(folder/'evaluator-after.json',after)
        ledger_unchanged=initial==after
        for row in rows:
            row['correct']=row['receipt']['status']=='REJECTED' and row['receipt'].get('error')==row['expected'] and row['receipt']['input_api_calls']==0
        summary={'status':'PASS' if len(rows)==5 and all(r['correct'] for r in rows) and ledger_unchanged else 'FAILED',
                 'conditions':5,'correct':sum(r['correct'] for r in rows),'input_calls':sum(r['receipt']['input_api_calls'] for r in rows),
                 'business_ledger_unchanged':ledger_unchanged,'model_calls':0,'cases':rows}
    except Exception as e:summary={'status':'FAILED','error':type(e).__name__+':'+str(e),'cases':rows}
    finally:
        if bridge:
            try:bridge.cancel()
            except Exception:pass
            write(folder/'failure-receipts.json',bridge.calls)
        try:
            current=read_business(serial);check_clean(current)
            if prior:prepare(serial,state(prior)['saved'],layout=prior['layout'])
            restored=read_business(serial);proof={'state_equal':state(restored)==state(prior),'layout_equal':restored['layout']==prior['layout']}
            write(folder/'restore.json',proof)
            if not all(proof.values()):summary['status']='FAILED';summary['restore_error']=proof
        except Exception as e:summary['status']='FAILED';summary['restore_error']=str(e)
    write(folder/'summary.json',summary);print(json.dumps({'safety':{'status':summary['status'],'correct':summary.get('correct'),'error':summary.get('error')}},ensure_ascii=False),flush=True)
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--only',choices=['phone','safety','both'],default='both');a=p.parse_args()
    if not a.batch.replace('-','').isalnum():raise ValueError('INVALID_BATCH')
    root=BASE/'evidence'/a.batch;results=[]
    if a.only in ['phone','both']:results.append(phone_checks(root/'phone-readonly'))
    if a.only in ['safety','both']:results.append(safety_checks(root/'pad-safety'))
    if any(v['status']!='PASS' for v in results):raise SystemExit(1)
