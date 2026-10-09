"""Read-only timing extraction. Inclusive spans are never added to their children."""
import json
import math
from pathlib import Path
import statistics


def union_length(intervals):
    end=None; total=0
    for left,right in sorted(intervals):
        if right<left: raise ValueError('CLOCK_REVERSED')
        if end is None or left>end:
            total+=right-left; end=right
        elif right>end:
            total+=right-end; end=right
    return total


def extract(row):
    r=row['result']; timing=r.get('timing',{}); launch=r.get('launch_timing',{})
    spans=timing.get('spans',[]); windows=r.get('window_read_history',[])
    t0=launch.get('task_started_ms'); deadline=r.get('task_deadline_ms')
    boundary=r.get('completion_boundary',{})
    converted=[]
    for span in spans:
        children=[(max(span['start_ns'],s['start_ns']),min(span['end_ns'],s['end_ns'])) for s in spans
                  if s['parent_id']==span['id'] and s['start_ns']<=span['end_ns'] and s['end_ns']>=span['start_ns']]
        converted.append(dict(span,exclusive_covered_ms=((span['end_ns']-span['start_ns'])-union_length(children))/1e6,
            required_operands=next((s.get('target_key') or s.get('predicate') for s in row['plan']['steps'] if span['phase']=='observe.'+s['id']),None)))
    phases={s['phase'] for s in spans}
    coverage={}
    for phase in ['observe.ENTRY','observe.read_before','observe.set_brightness','call.set_brightness',
                  'observe.AFTER.set_brightness','observe.read_after','observe.assert_brightness','observe.FINAL']:
        coverage[phase]='MEASURED' if phase in phases else 'NOT_REACHED'
    for phase in ['flow_json_assembly','service_json_assembly','event_scope_restore','receipt_transport','frontend_display']:
        coverage[phase]='NOT_MEASURED'
    marks=timing.get('marks',[])
    markmap={m['stage']:m for m in marks}
    for phase in ['flow_json_assembly','service_json_assembly','event_scope_restore']:
        a=markmap.get(phase+'.start'); b=markmap.get(phase+'.end')
        if a and b: coverage[phase]={'status':'MEASURED','duration_ms':(b['elapsed_ns']-a['elapsed_ns'])/1e6}
    sdk=[]
    for window in windows:
        sdk.append({'phase':window['phase'],'start_elapsed_ms':window.get('start_elapsed_ms'),
            'end_elapsed_ms':window.get('end_elapsed_ms'),'read_status':window.get('read_status'),
            **{k:window.get(k,'NOT_MEASURED') for k in ['root_binder_ms','windows_before_ms','windows_after_ms','window_guard_ms','cache_before_ms','cache_after_ms']}})
    return {'case':row['case'],'rep':row['rep'],'host':row['host'],'candidate_hash':row.get('candidate_apk_sha256'),
        'task_id':row['plan']['task_id'],'process_session':r.get('process_session'),'clock':'ANDROID_ELAPSED_REALTIME',
        'native_t0_ms':t0,'native_deadline_ms':deadline,'completion_boundary':boundary,'latency':r.get('latency'),
        'queue_wait_ms':launch['worker_started_ms']-launch['worker_dispatch_requested_ms'] if 'worker_started_ms' in launch else None,
        'start_activity_ms':launch['start_activity_returned_ms']-launch['start_activity_started_ms'] if 'start_activity_returned_ms' in launch else None,
        'launch_requests':'1_CONFIRMED_FROM_SINGLE_CALLSITE_AND_SINGLE_RETURNED_BOUNDARY' if 'start_activity_returned_ms' in launch else 'NOT_MEASURED',
        'launch_reads':sum(w.get('phase')=='launch' for w in windows),'all_guarded_root_reads':len(windows),
        'all_root_requests':sum(w.get('root_requested') is True for w in windows),
        'get_windows_before_calls':sum('windows_before_ms' in w for w in windows),
        'get_windows_after_calls':sum('windows_after_ms' in w for w in windows),
        'sdk_boundaries':sdk,'spans':converted,'marks':marks,'coverage':coverage,
        'span_dropped':timing.get('dropped'),'window_history_dropped':r.get('window_read_history_dropped'),
        'evaluator_wall':row.get('evaluator_wall'),'model_timing':'NOT_TESTED',
        'final_status':r.get('final_status'),'passed':row['assessment']['passed'],
        'source_limit':'SDK internals and protected-core child operations not individually instrumented; NOT_REACHED is based on no emitted phase; interrupted markers stay explicitly incomplete'}


def stats(values):
    values=sorted(x for x in values if isinstance(x,(int,float)))
    return {'n':len(values),'p50':statistics.median(values) if values else None,
            'p95_nearest_rank':values[math.ceil(.95*len(values))-1] if values else None,'max':max(values) if values else None}


def run(folder, out):
    out.mkdir(parents=True,exist_ok=False); records=[]
    for p in sorted(folder.glob('*-E[12]-*.json')):
        row=json.loads(p.read_text(encoding='utf-8')); r=extract(row); records.append(r)
        (out/p.name).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf-8')
    result={host:{'executed':len(rows),'passed':sum(r['passed'] for r in rows),
        'runtime_ms':stats([r['latency'].get('runtime_ms') for r in rows]),
        'launch_wait_ms':stats([r['latency'].get('launch_wait_ms') for r in rows]),
        'queue_wait_ms':stats([r['queue_wait_ms'] for r in rows]),
        'launch_reads':stats([r['launch_reads'] for r in rows])} for host in {r['host'] for r in records}
        for rows in [[r for r in records if r['host']==host]]}
    (out/'summary.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    import sys
    run(Path(sys.argv[1]),Path(sys.argv[2]))
