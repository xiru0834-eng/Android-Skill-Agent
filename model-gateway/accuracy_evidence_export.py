"""Offline response replay and framework-1 export. Never accesses API credentials."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from accuracy_confirmation import adjudicate,verify_protocol
from compiler import MODEL,ModelError
from evaluation_framework import VERSION,summarize
from selection_accuracy import select_accuracy
from start_teaching_bridge import resolve_selector
from workflow_experiment import write


def replay(root,index,row,pilot):
    folder=root/'trials'/f'{index:03d}-{row["strategy"]}';count=0
    def recorded(body):
        nonlocal count
        count+=1
        request=folder/(f'request-{count}.json' if pilot else 'request.json')
        response=folder/(f'response-{count}.json' if pilot else 'response.json')
        if json.loads(request.read_text(encoding='utf-8'))!=body:raise ValueError('REQUEST_CHANGED')
        if not response.exists() and not row['available'] and row.get('error')!='ValueError':
            raise ModelError(row['error'])
        raw=json.loads(response.read_text(encoding='utf-8'))
        if body['model']==MODEL and raw.get('returned_model')!=MODEL:raise ValueError('MODEL_CHANGED')
        return raw
    strategy=row['strategy'];case=row['case']
    try:
        selected=resolve_selector('gpt' if strategy=='G' else 'routed')(case['text'],case['skills'],recorded) if strategy in ['G','F'] else \
            select_accuracy(case['text'],case['skills'],recorded,recorded,review=strategy=='H')
    except (ValueError,ModelError) as exc:
        expected='ValueError' if isinstance(exc,ValueError) else str(exc)
        if row['available'] or row.get('error')!=expected:raise
        selected=None
    if count!=row['remoteCalls'] or (selected is not None)!=row['available'] or selected!=row.get('selection'):
        raise ValueError('DECISION_REPLAY_MISMATCH')


def export_campaign(root,out):
    root=Path(root);out=Path(out);protocol=json.loads((root/'protocol.json').read_text(encoding='utf-8'))
    verify_protocol(root,protocol);pilot=protocol.get('developmentRepairPilot',False)
    rows=json.loads((root/'results.json').read_text(encoding='utf-8')) if (root/'results.json').exists() else []
    caps=[dict(id='language.'+k,name=k) for k in ['zh','en','positive','negative']]
    plan=dict(schema=1,framework=VERSION,campaign='accuracy-'+root.name,variant='paired-selectors',
        phase='retrospective',capabilities=caps,cases=[])
    observations=[]
    for index,trial in enumerate(protocol['trials']):
        case=protocol['cases'][trial['index']];identity=f'{index:03d}-{trial["strategy"]}'
        dimensions=dict(dataset=root.name,app='finite-reviewed-catalog',device='not-executed',display=None,
            budget_ms=None if pilot else 45000,auditor='frozen-response-replay',changed_factor='selector',
            source_phase='development' if pilot else 'confirmation',language=case['language'],
            intent_cluster=case['conceptId'],catalog_variant=case['variant'])
        tags=['language.'+case['language'],'language.positive' if case['expected'] else 'language.negative']
        plan['cases'].append(dict(id=identity,stage='language',repeat=trial['repeat'],family=case['caseId'],
            environment=trial['strategy'],expected=case['expected'] or 'no-invoke',dimensions=dimensions,capabilities=tags))
        if index>=len(rows):continue
        row=copy.deepcopy(rows[index])
        try:
            if row['case']!=case or row['strategy']!=trial['strategy'] or row['repeat']!=trial['repeat']:
                raise ValueError('TRIAL_CHANGED')
            replay(root,index,row,pilot);adjudicate(row)
            observations.append(dict(case_id=identity,state='SCORED',checks=dict(decision_correct=row['correct']),
                metrics=dict(positive=case['expected'] is not None,false_invoke=row['unsafeSuggestion'],
                    availability=row['available'],remote_calls=row['remoteCalls'],decision_status=row.get('selection',{}).get('status'),
                    timings=dict(model_ms=row['ms'])),error=row.get('error',row['failureClass']),
                evidence_basis='frozen_provider_response_replay',evidence=str((root/'trials'/identity).resolve())))
        except (ValueError,KeyError,FileNotFoundError):
            observations.append(dict(case_id=identity,state='INVALID',error='RAW_EVIDENCE_OR_REPLAY_MISMATCH',metrics={}))
    report=summarize(plan,observations)
    report['languageSafetyAlerts']=['wrong_invocation'] if any(o.get('metrics',{}).get('false_invoke') for o in observations) else []
    report['scopeNote']='Language only. Import is retrospective; original protocols were frozen. No GUI completion claim. Pilot lacks a shared two-model deadline.'
    out.mkdir(parents=True,exist_ok=False)
    write(out/'plan.json',plan);write(out/'observations.json',observations);write(out/'report.json',report)
    write(out/'evidence-sha256.json',{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob('*')) if p.is_file()})
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=export_campaign(a.source,a.output);print(json.dumps(result['stages']['language']['states']))
