"""Evaluator orchestration; controller gets public UI only, never private answers.
Separate folders retain raw native receipts and independent business-state ledger.
"""
import argparse
import json
import time
from pathlib import Path
from android_bridge import AndroidBridge,SERIALS
from evaluation_device import read_business,state,check_clean,prepare,audit_delta
from navigation_controller import observe,navigate
from native_materials import validate_native_interaction,native_bundle
from bundle_contract import need
from bundle_store import BundleStore
from learning_queries import LearningQueries

BASE=Path(__file__).resolve().parent
ENV={'app_package':'edu.sydney.transferlab','app_build':'6','environment_id':'existing-workflow-lab',
     'ui_revision':'native-multi-v6','domain':'EXPERIMENT_APP'}

def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def run(serial,batch,repeat,*,delay=False):
    folder=BASE/'evidence'/batch/(serial+'-r'+str(repeat)+('-delay' if delay else ''))
    folder.mkdir(parents=True,exist_ok=False)
    prior=read_business(serial);check_clean(prior);write(folder/'evaluator-prior-state.json',prior)
    saved=state(prior)['saved'] if prior else [0,40,0,3]
    bridge=AndroidBridge(serial);observations=[];steps=[];status='FAILED';error=None;started=time.monotonic()
    try:
        prepare(serial,saved,layout='multi',fault='navdelay' if delay else 'normal')
        initial=read_business(serial);check_clean(initial);write(folder/'evaluator-initial-state.json',initial)
        need(bridge.start('edu.sydney.transferlab')['status']=='STARTED','SCOPE_START_FAILED')
        before=observe(bridge);observations.append(before)
        for text,expected_page in zip(['Reading lamp','Back','Desk fan','Back'],['lamp','overview','fan','overview']):
            real_before=read_business(serial)
            t=navigate(bridge,before,text);real_after=read_business(serial)
            # Independent evaluator owns the expected answer; controller only received public command text.
            need(real_after['events'][-1]['page']==expected_page,'WRONG_NAVIGATION_DESTINATION')
            t['business_audit']=audit_delta(real_before,real_after);validate_native_interaction(t)
            write(folder/('evaluator-step-'+str(len(steps)+1)+'.json'),{'before':real_before,'after':real_after})
            steps.append(t);before=t['after'];observations.append(before)
        final=read_business(serial);summary_audit=audit_delta(initial,final)
        need(summary_audit['write_count']==0 and summary_audit['pending_count']==0 and summary_audit['state_unchanged'],'UNSAFE_BUSINESS_CHANGE')
        write(folder/'evaluator-final-state.json',final)
        bundle=native_bundle(observations,steps,ENV)
        write(folder/'learning-bundle.json',bundle)
        # A readable tree plus successful clicks cannot substitute for page/entity memory.
        need(len(bundle['pages'])==3 and all(p['identity_status']=='KNOWN' and p['entities'] for p in bundle['pages'])
             and {p['navigation_context']['page_hint'] for p in bundle['pages']}=={'overview','lamp','fan'},'PAGE_IDENTITY_INCOMPLETE')
        db=folder/'memory.sqlite'
        with BundleStore(db,create=True) as store:stored=store.append(bundle,expected_revision=0)
        with BundleStore(db,read_only=True) as store:
            audit_before=bridge.events();query_before_business=read_business(serial)
            q=LearningQueries(store);pages=q.list_pages(ENV)
            pid=pages['items'][0]['page_id'];detail=q.inspect_page(ENV,pid);region=q.inspect_region(ENV,pid,detail['page']['regions'][0]['region_id'])
            targets=q.search_semantic_targets(ENV,text='Back')
            queries={'list_pages':pages,'inspect_page':detail,'inspect_region':region,'search_semantic_targets':targets}
            need(len(pages['items'])==3 and all(v['execution_authority'] is False and v['implicit_observe_calls']==0 and v['device_action_calls']==0 for v in queries.values()),'QUERY_CONTRACT_ERROR')
            write(folder/'query-results.json',queries)
            audit_after=bridge.events();query_after_business=read_business(serial)
            proof={'native_counters_unchanged':audit_before['counters']==audit_after['counters'],
                   'business_ledger_unchanged':query_before_business==query_after_business,
                   'query_calls':4,'device_actions':0,'implicit_observe_calls':0,'network_calls':0}
            need(proof['native_counters_unchanged'] and proof['business_ledger_unchanged'],'READONLY_QUERY_SIDE_EFFECT')
            write(folder/'real-query-readonly-proof.json',proof)
        stopped=bridge.stop();need(stopped['status']=='STOPPED','SCOPE_STOP_FAILED')
        status='PASS'
    except Exception as e:error=type(e).__name__+':'+str(e)
    finally:
        if status!='PASS' and bridge.scope_id:
            try:bridge.cancel()
            except Exception:pass
        # Only evaluator owns restoration. Preserve saved state, restore the prior UI mode/fault.
        try:
            current=read_business(serial);check_clean(current)
            prepare(serial,saved,layout=prior.get('layout','single') if prior else 'single')
            restored=read_business(serial)
            restore={'saved_state_preserved':state(restored)['saved']==saved,'draft_clean':state(restored)['draft']==saved,
                     'pending_zero':state(restored)['pending']==0,'layout':restored.get('layout')}
            write(folder/'restore.json',restore)
            if not all(restore[k] for k in ['saved_state_preserved','draft_clean','pending_zero']):status='FAILED';error='RESTORE_FAILED'
        except Exception as e:status='FAILED';error='RESTORE_ERROR:'+str(e)
        write(folder/'native-receipts.json',bridge.calls)
        write(folder/'partial-observations.json',observations);write(folder/'partial-interactions.json',steps)
        summary={'status':status,'error':error,'serial':serial,'repeat':repeat,'delay':delay,'observations':len(observations),
            'real_navigation_actions':sum(v.get('input_api_calls',0) for v in bridge.calls),'interactions_verified':len(steps),
            'model_calls':0,'latency_ms':round((time.monotonic()-started)*1000,3),'folder':str(folder),
            'counts_are_repetitions_not_independent_generalization_scenarios':True}
        write(folder/'summary.json',summary)
    print(json.dumps(summary,ensure_ascii=False),flush=True);return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--serial',choices=sorted(SERIALS),required=True)
    p.add_argument('--repeat',type=int,default=1);p.add_argument('--delay',action='store_true');a=p.parse_args()
    if not a.batch.replace('-','').isalnum():raise ValueError('INVALID_BATCH')
    result=run(a.serial,a.batch,a.repeat,delay=a.delay)
    if result['status']!='PASS':raise SystemExit(1)
