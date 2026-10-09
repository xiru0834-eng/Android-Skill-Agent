"""Reproducible final scoring and time accounting; never dispatches tasks or calls models."""
import hashlib,json,math,statistics
from pathlib import Path
from repair_scorer import score,ledger
from prepare_g1 import save
ROOT=Path(__file__).parent
RUN=ROOT/'evidence/flow-deadline-repair/r1'
def load(p):return json.loads(p.read_text(encoding='utf-8'))
def distribution(values):
    v=sorted(values)
    return {'n':len(v),'p50':statistics.median(v) if v else None,'p95_nearest_rank':v[max(0,math.ceil(len(v)*.95)-1)] if v else None,'max':max(v) if v else None}
def spans(result):
    rows=result.get('timing',{}).get('spans',[]);totals={}
    for s in rows:
        children=[x for x in rows if x.get('parent_id')==s['id'] and x['start_ns']>=s['start_ns'] and x['end_ns']<=s['end_ns']]
        exclusive=max(0,s['duration_ms']-sum(x['duration_ms'] for x in children))
        t=totals.setdefault(s['phase'],{'count':0,'inclusive_ms':0,'exclusive_ms':0});t['count']+=1;t['inclusive_ms']+=s['duration_ms'];t['exclusive_ms']+=exclusive
    return {'totals':totals,'dropped':result.get('timing',{}).get('dropped'),
        'warning':'Inclusive parents overlap children; not a total. Dropped spans prevent exact exclusive accounting.',
        'window_reads':[{k:r.get(k) for k in ('phase','start_elapsed_ms','end_elapsed_ms','read_status','root_binder_ms','windows_before_ms','windows_after_ms','window_guard_ms','viewport_context_ms','viewport_metrics_ms')} for r in result.get('window_read_history',[])]}
def run():
    out=RUN/'final-v97-confirmation-r2';out.mkdir(parents=True,exist_ok=False);scores=[];channels={};times=[]
    for name,host in [('final-phone','R5CW134LLBZ'),('final-emulator','emulator-5556'),('repeat-emulator-1','emulator-5556'),('repeat-emulator-2','emulator-5556')]:
        d=RUN/'real-nl'/('v97-'+name+'-r2');registered=load(d/'registered-cases.json') if (d/'registered-cases.json').exists() else []
        actual=[]
        for case in registered:
            p=d/(case['name']+'.json')
            if not p.exists():continue
            row=load(p);scored=score(row);r=row.get('ui',{}).get('result',{});actual.append(row)
            scores.append({'batch':name,'host':host,'case':row['case'],'expected':row['expected'],'actual':row['final_status'],'source':str(p),'score':scored})
            rid=row.get('ui',{}).get('selection',{}).get('request_id');audit_path=next((p for p in d.rglob(str(rid)+'.json')),None) if rid else None
            model_timing=load(audit_path).get('timings_ns') if audit_path else None
            times.append({'batch':name,'host':host,'case':row['case'],'status':row['final_status'],'expected':row['expected'],
                'whole_frontend_ms':row.get('latency_ms'),'native':r.get('latency'), 'time_account':spans(r),
                'frontend_timings_ns':row.get('ui',{}).get('timings_ns'),'model_timings_ns':model_timing,
                'unmeasured':'No exact historical queue/tree-copy/input dispatch/result callback split; no invented times.'})
        channel={'planned':8 if name.startswith('final-') else 2,'executed':len(actual),'passed':sum(score(r)['passed'] for r in actual),
            'positive_modification_success':sum(score(r)['passed'] and r['expected']=='SUCCESS' for r in actual),
            'positive_modification_total':sum(r['expected']=='SUCCESS' for r in actual),
            'noop_success':sum(score(r)['passed'] and r['expected']=='NO_ACTION_REQUIRED' for r in actual),
            'noop_total':sum(r['expected']=='NO_ACTION_REQUIRED' for r in actual),
            'task_ledger':ledger([{'result':r.get('ui',{}).get('result',{})} for r in actual],8 if name.startswith('final-') else 2)}
        native=[r.get('ui',{}).get('result',{}).get('latency',{}).get('runtime_ms') for r in actual if r['expected']=='SUCCESS']
        channel['native_modification_latency_ms']=distribution([v for v in native if v is not None]);channels[name]=channel
    models=[]
    for p in RUN.rglob('paid-budget.json'):
        r=load(p);models.append({'path':str(p),'attempts':r['attempts'],'exposure_nano_usd':r['exposureNanoUsd'],'ledger':r})
    save(out/'scores.json',scores);save(out/'timing.json',times)
    save(out/'model-ledger.json',{'sessions':models,'attempts':sum(r['attempts'] for r in models),'estimated_or_reserved_usd':sum(r['exposure_nano_usd'] for r in models)/1e9,
        'actual_invoice':'UNKNOWN','authorized_attempt_cap':32,'authorized_estimate_cap_usd':1,'automatic_retry':False})
    freeze=load(RUN/'freeze-v97-confirmation-r2/freeze.json')
    changed=[name for name,h in freeze['source'].items() if not (ROOT/name).exists() or hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=h]
    external_changed=[name for name,h in freeze['external_python_sources'].items() if not Path(name).exists() or hashlib.sha256(Path(name).read_bytes()).hexdigest()!=h]
    capsule_changed=[name for name,h in freeze['published_capsules'].items() if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=h]
    save(out/'freeze-readback.json',{'source_changed_after_freeze':changed,'external_sources_changed':external_changed,'published_capsules_changed':capsule_changed,'apk_matches_freeze':hashlib.sha256(Path(freeze['apk']).read_bytes()).hexdigest()==freeze['apk_sha256']})
    save(out/'summary.json',{'channels':channels,'wrong_action':sum(s['score']['wrong_action'] for s in scores),'false_success':sum(s['score']['false_success'] for s in scores),
        'all_real_nl_passed':len(scores)==20 and all(s['score']['passed'] for s in scores),'scope':'FROZEN_FLOW_TIMEOUT_REPAIR_NOT_ENTIRE_P3_P5',
        'no_post_freeze_source_change':not changed,'time_quantile':'P95 nearest rank; no-action excluded from modification latency'})
    print(json.dumps(channels,ensure_ascii=False),flush=True)
if __name__=='__main__':run()
