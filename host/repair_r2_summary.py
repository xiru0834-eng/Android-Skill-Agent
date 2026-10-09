"""Read-only independent scoring, timing, and frozen-source read-back for continuation r2."""
import hashlib,json
from pathlib import Path
from prepare_g1 import save
from repair_scorer import score,ledger
from report_deadline_repair import distribution,spans
ROOT=Path(__file__).parent
RUN=ROOT/'evidence/flow-deadline-repair/r2'
load=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()

def run(label='v102'):
    out=RUN/('final-'+label);out.mkdir(parents=True,exist_ok=False)
    scores=[];channels={};times=[]
    for phase in ('final-phone','final-emulator','repeat-phone-1','repeat-phone-2','repeat-emulator-1','repeat-emulator-2'):
        folder=RUN/'real-nl'/(label+'-'+phase)
        planned=8 if phase.startswith('final-') else 2
        rows=[]
        for spec in load(folder/'registered-cases.json') if (folder/'registered-cases.json').exists() else []:
            path=folder/(spec['name']+'.json')
            if not path.exists():continue
            row=load(path);rows.append(row);scored=score(row);r=row.get('ui',{}).get('result',{})
            scores.append({'phase':phase,'host':row['host'],'case':row['case'],'expected':row['expected'],
                 'actual':row['final_status'],'source':str(path),'score':scored})
            times.append({'phase':phase,'host':row['host'],'case':row['case'],'expected':row['expected'],
                 'status':row['final_status'],'whole_frontend_ms':row.get('latency_ms'),
                 'native':r.get('latency'),'launch_timing':r.get('launch_timing'),'time_account':spans(r)})
        channels[phase]={'planned':planned,'executed':len(rows),'passed':sum(score(r)['passed'] for r in rows),
             'modification_passed':sum(score(r)['passed'] and r['expected']=='SUCCESS' for r in rows),
             'modification_total':sum(r['expected']=='SUCCESS' for r in rows),
             'noop_passed':sum(score(r)['passed'] and r['expected']=='NO_ACTION_REQUIRED' for r in rows),
             'noop_total':sum(r['expected']=='NO_ACTION_REQUIRED' for r in rows),
             'modification_latency_ms':distribution([r['ui']['result']['latency']['runtime_ms'] for r in rows
                 if r['expected']=='SUCCESS' and 'latency' in r['ui'].get('result',{})]),
             'ledger':ledger([{'result':r.get('ui',{}).get('result',{})} for r in rows],planned)}
    g1=[]
    refused={'missing_authority':('REJECTED','VALIDATION_AUTHORITY_REQUIRED'),
             'unauthorized_write':('REJECTED','UNAUTHORIZED_WRITE'),
             'missing_target':('UNCONFIRMED','MISSING_TARGET'),
             'ambiguous':('UNCONFIRMED','AMBIGUOUS_ID'),
             'illegal_later':('REJECTED','VALUE_RANGE'),
             'cancel_before_input':('CANCELLED','CANCELLED')}
    for folder in (RUN/'regression').glob(label+'-g1-*'):
        rows=[]
        for p in folder.glob('*.json'):
            if p.name=='summary.json':continue
            r=load(p);native=r['result'];name=r['case'];contract=True
            if name in refused:contract=(native.get('final_status'),native.get('reason'))==refused[name] and not native.get('execution_actions')
            if name in {'changed','already','delay_500','ordered_same_final'}:
                contract=native.get('final_observation_complete') is True and native.get('verification_result') is True
                contract=contract and native.get('latency',{}).get('runtime_ms',999999)<8000
                contract=contract and all(s.get('status')=='VERIFIED' for s in native.get('steps',[]))
                contract=contract and native.get('final_observed_state')==r['after']['state']
                action_values=[a['value'] for a in native.get('execution_actions',[])]
                contract=contract and action_values==({'changed':[80],'already':[],'delay_500':[80],'ordered_same_final':[20,50]}[name])
            if name=='no_effect':
                contract=native.get('final_status') in {'BUDGET_EXCEEDED','UNCONFIRMED','FAILED','PARTIAL'} and native.get('verification_result') is False
                contract=contract and [a['value'] for a in native.get('execution_actions',[])]==[80]
            rows.append({'case':name,'source':str(p),'old_assessment':r['assessment'],
                         'additional_contract':bool(contract),'passed':bool(r['assessment']['passed'] and contract)})
        g1.append({'host':folder.name.removeprefix(label+'-g1-'),'planned':11,'executed':len(rows),
                   'passed':sum(r['passed'] for r in rows),'rows':rows})
    model_sessions=[{'path':str(p),'ledger':load(p)} for p in RUN.rglob('paid-budget.json')]
    freeze=load(RUN/('freeze-'+label)/'freeze.json')
    changed=[p for p,h in freeze['source'].items() if not (ROOT/p).exists() or sha(ROOT/p)!=h]
    external=[p for p,h in freeze['external_python_sources'].items() if not Path(p).exists() or sha(Path(p))!=h]
    capsules=[p for p,h in freeze['published_capsules'].items() if sha(Path(p))!=h]
    save(out/'scores.json',scores);save(out/'timing.json',times);save(out/'strict-g1.json',g1)
    save(out/'model-ledger.json',{'sessions':model_sessions,'attempts':sum(r['ledger']['attempts'] for r in model_sessions),
         'estimated_or_reserved_usd':sum(r['ledger']['exposureNanoUsd'] for r in model_sessions)/1e9,
         'actual_invoice':'UNKNOWN','automatic_retry':False,'max_attempts':32,'estimated_cap_usd':1})
    save(out/'freeze-readback.json',{'source_changed':changed,'external_changed':external,'capsule_changed':capsules,
         'apk_matches_freeze':sha(Path(freeze['apk']))==freeze['apk_sha256']})
    summary={'channels':channels,'real_planned':24,'real_executed':len(scores),
         'real_strict_passed':sum(s['score']['passed'] for s in scores),'wrong_action':sum(s['score']['wrong_action'] for s in scores),
         'false_success':sum(s['score']['false_success'] for s in scores),'all_real_passed':len(scores)==24 and all(s['score']['passed'] for s in scores),
         'g1':[{k:v for k,v in r.items() if k!='rows'} for r in g1],'frozen_source_unchanged':not(changed or external or capsules)}
    save(out/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--label',default='v102');args=parser.parse_args();run(args.label)
