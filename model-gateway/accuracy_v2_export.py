"""Offline raw-response replay of H2 and retrospective framework export."""
import argparse
import copy
import hashlib
import json
import shutil
from pathlib import Path
from accuracy_confirmation import adjudicate,verify_protocol
from accuracy_v2 import summarize as campaign_summary
from selection_deadline import SelectionBudget,select_bounded
from compiler import MODEL,ModelError
from evaluation_framework import VERSION,summarize
from workflow_experiment import write


class EvidenceError(RuntimeError):
    pass


def replay(root,index,row):
    folder=root/'trials'/f'{index:03d}-{row["strategy"]}';count=0;now=[0.]
    budget=SelectionBudget(8,clock=lambda:now[0],max_calls=1 if row['strategy']=='G' else 2)
    def recorded(body,timeout):
        nonlocal count
        count+=1;entry=row['calls'][count-1]
        if json.loads((folder/f'request-{count}.json').read_text(encoding='utf-8'))!=body:
            raise EvidenceError('REQUEST_CHANGED')
        if abs(timeout-entry['timeoutSeconds'])>.15:raise EvidenceError('BUDGET_REPLAY_MISMATCH')
        now[0]+=entry['elapsedMs']/1000
        response=folder/f'response-{count}.json'
        if not response.exists():
            if entry['outcome']=='RETURNED':raise EvidenceError('MISSING_RESPONSE')
            if entry['outcome'] in ['SELECTION_CANCELLED','STALE_REQUEST']:
                raise EvidenceError('CANCEL_REQUIRES_SEPARATE_FAULT_AUDIT')
            raise ModelError(entry['outcome'])
        raw=json.loads(response.read_text(encoding='utf-8'))
        if body['model']==MODEL and raw.get('returned_model')!=MODEL:raise EvidenceError('MODEL_CHANGED')
        return raw
    selected=None;error=None
    try:selected=select_bounded(row['strategy'],row['case']['text'],row['case']['skills'],budget,recorded,recorded)
    except (ValueError,ModelError) as exc:error=str(exc) if isinstance(exc,ModelError) else type(exc).__name__
    if selected!=row.get('selection') or count!=row['remoteCalls'] or error!=row.get('error'):
        raise ValueError('DECISION_REPLAY_MISMATCH')


def export(root,out):
    protocol=json.loads((root/'protocol.json').read_text(encoding='utf-8'));verify_protocol(root,protocol)
    rows=json.loads((root/'results.json').read_text(encoding='utf-8'))
    plan=dict(schema=1,framework=VERSION,campaign='accuracy-confirmation-v2',variant='G-v-H2',phase='retrospective',
        capabilities=[dict(id='language.'+k,name=k) for k in ['zh','en','positive','negative']],cases=[])
    observations=[]
    for index,trial in enumerate(protocol['trials']):
        case=protocol['cases'][trial['index']];identity=f'{index:03d}-{trial["strategy"]}'
        plan['cases'].append(dict(id=identity,stage='language',repeat=trial['repeat'],family=case['caseId'],
            environment=trial['strategy'],expected=case['expected'] or 'no-invoke',
            capabilities=['language.'+case['language'],'language.positive' if case['expected'] else 'language.negative'],
            dimensions=dict(device='not-executed',budget_ms=8000,language=case['language'],intent_cluster=case['conceptId'],
                catalog_variant=case['variant'],changed_factor='selector')))
        if index>=len(rows):continue
        row=copy.deepcopy(rows[index])
        try:
            if row['case']!=case or row['strategy']!=trial['strategy'] or row['repeat']!=trial['repeat']:
                raise ValueError('TRIAL_CHANGED')
            if json.loads((root/'trials'/identity/'row.json').read_text(encoding='utf-8'))!=row:raise ValueError('ROW_CHANGED')
            replay(root,index,row);adjudicate(row)
            observations.append(dict(case_id=identity,state='SCORED',checks=dict(decision_correct=row['correct']),
                metrics=dict(positive=case['expected'] is not None,false_invoke=row['unsafeSuggestion'],
                    availability=row['available'],remote_calls=row['remoteCalls'],timings=dict(model_ms=row['ms'])),
                error=row.get('error',row['failureClass']),evidence_basis='recorded_response_and_budget_replay',
                evidence=str((root/'trials'/identity).resolve())))
        except (EvidenceError,ValueError,KeyError,FileNotFoundError,IndexError):
            observations.append(dict(case_id=identity,state='INVALID',error='RAW_EVIDENCE_OR_REPLAY_MISMATCH',metrics={}))
    report=summarize(plan,observations)
    report['scopeNote']='Selection only; raw replay is retrospective. No new API or GUI completion evidence.'
    report['languageSafetyAlerts']=['wrong_invocation'] if any(o.get('metrics',{}).get('false_invoke') for o in observations) else []
    out.mkdir(parents=True,exist_ok=False)
    for name,data in [('plan',plan),('observations',observations),('report',report),('campaign-summary',campaign_summary(rows,protocol))]:
        write(out/(name+'.json'),data)
    write(out/'evidence-sha256.json',{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob('*')) if p.is_file()})
    shutil.copy2(Path(__file__),out/'auditor-source.py')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    result=export(a.source,a.output);print(json.dumps(result['stages']['language']['states']))
