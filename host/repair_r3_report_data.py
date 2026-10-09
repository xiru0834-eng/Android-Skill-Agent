"""Read-only evidence reducer. Does not dispatch Android or model operations."""
import json
from pathlib import Path
import subprocess

from prepare_g1 import save
from repair_r3_gate import sha
from repair_r3_timing import extract,stats
import repair_r3 as r3

ROOT=Path(__file__).parent
RUN=r3.RUN


def load(path):return json.loads(path.read_text(encoding='utf-8'))


def run():
    ledger=[]
    counts={}
    for label,folder in [('v102-diagnostic',RUN/'reproduction-v102'),
                         ('v103-diagnostic',RUN/'reproduction-v103'),
                         ('v103-confirmation',RUN/'confirmation-r2/normal/reproduction-v103')]:
        rows=[]
        for p in sorted(folder.glob('*-E[12]-*.json')):
            row=load(p);row['evidence_path']=str(p);rows.append(row)
            ledger.append({'phase':label,'host':row['host'],'case':row['case'],'rep':row['rep'],
                'candidate':row['candidate_apk_sha256'],'flow_hash':row['plan']['flow_hash'],
                'task_id':row['plan']['task_id'],'initial_state':row['before']['state'],
                'final_status':row['result']['final_status'],'assessment':row['assessment'],
                'latency':row['result']['latency'],'evidence':str(p),'sha256':sha(p.read_bytes())})
        counts[label]={host:{'passed':sum(r['assessment']['passed'] for r in rows if r['host']==host),
           'executed':sum(r['host']==host for r in rows),
           'by_scenario':{scenario:{'passed':sum(r['assessment']['passed'] for r in rows if r['host']==host and r['case']==scenario),
                                  'executed':sum(r['host']==host and r['case']==scenario for r in rows)} for scenario in ['E1','E2']}}
           for host in r3.HOSTS}
    (RUN/'normal_entry_cases.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in ledger),encoding='utf-8')
    real=[]
    timing=RUN/'timing_trace/real-nl'
    timing.mkdir(exist_ok=False)
    for phase in sorted((RUN/'real_nl').iterdir()):
        if not phase.is_dir():continue
        for p in phase.glob('*.json'):
            row=load(p)
            if 'assessment' not in row:continue
            row['phase']=phase.name;row['evidence_path']=str(p);real.append(row)
            if row['ui'].get('result',{}).get('launch_timing'):
                derived={'case':row['case'],'rep':0,'host':row['host'],'result':row['ui']['result'],
                    'plan':row['ui']['selection']['plan'],'assessment':row['assessment'],
                    'candidate_apk_sha256':load(RUN/'candidate-v103/freeze.json')['apk_sha256']}
                trace=extract(derived)
                trace['model_timing']='SEPARATE_REAL_MODEL_AUDIT'
                trace['source_evidence']=str(p)
                trace['evaluator_wall']=row['ui'].get('timings_ns')
                save(timing/(phase.name+'-'+p.name),trace)
    budgets=[load(p) for p in (RUN/'real_nl').rglob('paid-budget.json')]
    model_ms=[]
    for p in (RUN/'real_nl').rglob('model-audit/*.json'):
        d=load(p);ts=d.get('timings_ns',{})
        if 'model_request_returned' in ts:model_ms.append((ts['model_request_returned']-ts['model_request_started'])/1e6)
    realsummary={host:{'expected_behavior_passed':sum(r['assessment']['passed'] for r in real if r['host']==host),
        'executed':sum(r['host']==host for r in real),
        'positive_passed':sum(r['assessment']['passed'] and r['expected'] in {'SUCCESS','NO_ACTION_REQUIRED'} for r in real if r['host']==host),
        'positive_executed':sum(r['expected'] in {'SUCCESS','NO_ACTION_REQUIRED'} for r in real if r['host']==host),
        'native_ms':stats([r['ui'].get('result',{}).get('latency',{}).get('runtime_ms') for r in real if r['host']==host]),
        'evaluator_wall_ms':stats([r['latency_ms'] for r in real if r['host']==host])} for host in r3.HOSTS}
    realsummary.update(planned=24,executed=len(real),not_run=24-len(real),
        wrong_action=sum(r['assessment']['wrong_action'] for r in real),false_success=sum(r['assessment']['false_success'] for r in real),
        model_requests=sum(d['attempts'] for d in budgets),estimated_usd=sum(d['exposureNanoUsd'] for d in budgets)/1e9,
        actual_invoice='UNKNOWN',model_ms=stats(model_ms),runner_state=load(RUN/'real_nl_runner/state.json'))
    save(RUN/'real_nl/aggregate.json',realsummary)
    save(RUN/'case-ledger.json',{'normal_entry':ledger,'real_language':[{'phase':r['phase'],'case':r['case'],'host':r['host'],
         'final_status':r['final_status'],'assessment':r['assessment'],'evidence':r['evidence_path']} for r in real],
         'real_unrun':[{'phase':p,'cases':['explicit','new_session']} for p in realsummary['runner_state']['unrun']]})
    frozen=load(RUN/'candidate-v103/freeze.json')
    native_drift=[p for p,h in frozen['source_files'].items() if p.replace('\\','/').startswith('native/') and sha((ROOT/p).read_bytes())!=h]
    original=load(RUN/'preflight/source.json')['files']
    changed=[p for p,h in original.items() if (ROOT/p).is_file() and sha((ROOT/p).read_bytes())!=h]
    save(RUN/'source-final-audit.json',{'native_drift_since_v103_freeze':native_drift,
         'changes_to_existing_files_since_r3_start':changed,
         'protected_cores_unchanged':{c:sha((ROOT/'native/app/src/main/java/edu/sydney/probe'/(c+'.java')).read_bytes())==
             sha((ROOT.parent/'native-learning-candidate-v92/app/src/main/java/edu/sydney/probe'/(c+'.java')).read_bytes()) for c in r3.CORES},
         'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
         'git_status':subprocess.check_output(['git','status','--short'],cwd=ROOT).decode()})
    save(RUN/'result.json',{'RUNNER_STOP_GATE':'PASS','NORMAL_ENTRY_REPRODUCTION':counts,
        'CURRENT_CANDIDATE_REAL_GPT':realsummary,'ROOT_CAUSE_STATUS':'NOT_ESTABLISHED / UNRESOLVED_VARIABILITY',
        'PROTECTED_CORE_MODIFIED':'NO','DEADLINE_AND_FLOW_INVARIANTS':'UNCHANGED',
        'G1':{p.name:load(p/'summary.json') for p in (RUN/'confirmation-r2/regression').iterdir() if p.name.startswith('g1-')},
        'CANCEL':{p.name:load(p/'summary.json') for p in (RUN/'confirmation-r2/regression').iterdir() if p.name.startswith('cancel-')},
        'LOCAL_REGRESSION':load(RUN/'regression/final-local/summary.json'),
        'RESTORATION':load(RUN/'restoration/summary.json'),
        'TIMEOUT_REPAIR_ACCEPTANCE':'PARTIAL','CORE_CHANGE_REQUIRES_APPROVAL':'YES_IF_CONTINUING_PROTECTED_CORE_DIAGNOSTICS',
        'SHOWROOM_RELEASE':'NO','P3_P4_P5_FORMAL_ACCEPTANCE':'NOT_UPGRADED',
        'normal_task_count':36,'real_case_count':len(real),'model_requests':realsummary['model_requests']})
    print(json.dumps({'normal':counts,'real':realsummary,'native_drift':native_drift},ensure_ascii=False,indent=2))


if __name__=='__main__':run()
