"""Bounded GPT-only real-catalog phase confirmation; never sends Android inputs."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import statistics
from accuracy_confirmation import adjudicate, verify_protocol
from accuracy_v2 import measure
from closeout_cases import SPECS
from compiler import MODEL
from deadline_remote import gpt_remote
from model_coordination import percentile
from paid_budget import PaidBudget
from skill_selection import validate_catalog
from workflow_experiment import write

SOURCES=['closeout_confirmation.py','closeout_cases.py','paid_budget.py','accuracy_v2.py',
    'accuracy_confirmation.py','model_coordination.py','skill_selection.py','catalog_uniqueness.py',
    'selection_deadline.py','selection_accuracy.py','deadline_remote.py','compiler.py','contracts.py']


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True).encode('utf-8')).hexdigest()


def cases_for(base):
    base=copy.deepcopy(validate_catalog(base));ids={tuple(s['finalGoals']):s['id'] for s in base}
    result=[]
    for index,(key,category,target,zh,en) in enumerate(SPECS):
        skills=base if index%2==0 else list(reversed(base))
        for lang,text in [('zh',zh),('en',en)]:
            result.append(dict(caseId=key+'-'+lang,conceptId=key,category=category,
                language=lang,text=text,expected=ids[target] if target else None,skills=copy.deepcopy(skills),
                acceptableStatuses=['invoke'] if target else ['clarify','reject'],
                labelBasis='Exact named immutable skill or complete exact goals' if target else 'No immediate permitted unique unchanged skill'))
    return result


def summary(rows):
    def group(data):
        pos=[r for r in data if r['case']['expected']];neg=[r for r in data if r['case']['expected'] is None]
        times=[r['ms'] for r in data]
        return dict(n=len(data),positiveN=len(pos),positiveCorrect=sum(r['correct'] for r in pos),
            negativeN=len(neg),negativeCorrect=sum(r['correct'] for r in neg),available=sum(r['available'] for r in data),
            unsafeSuggestions=sum(r['unsafeSuggestion'] for r in data),p50ms=statistics.median(times) if times else None,
            p95ms=percentile(times,.95),maxMs=max(times) if times else None)
    stats=group(rows);stats.update(planned=180,notRun=180-len(rows),overall='NOT_READY',
        selectionOnly=True,actualSavedCatalogOnly=True,authorLabelledNotIndependentHumanGold=True,
        language={lang:group([r for r in rows if r['case']['language']==lang]) for lang in ['zh','en']},
        byCategory={c:group([r for r in rows if r['case']['category']==c]) for c in sorted({r['case']['category'] for r in rows})})
    gate=lambda v:v['positiveN']>0 and v['positiveCorrect']/v['positiveN']>=.95 and v['negativeN']>0 and v['negativeCorrect']/v['negativeN']>=.95
    stats['stageLanguageGate']=len(rows)==180 and stats['unsafeSuggestions']==0 and stats['available']/180>=.98 and gate(stats) and all(gate(v) for v in stats['language'].values())
    buckets=[[r for r in rows if r['case']['caseId']==key] for key in {r['case']['caseId'] for r in rows}]
    stats['expressionsAllThreeCorrect']=sum(len(v)==3 and all(r['correct'] for r in v) for v in buckets)
    stats['failures']=[dict(caseId=r['case']['caseId'],repeat=r['repeat'],failure=r['failureClass'],error=r.get('error')) for r in rows if not r['correct']]
    return stats


def freeze(out,base):
    cases=cases_for(base);prior=set();root=Path(__file__).parents[1]/'output'
    for name in ['accuracy-confirmation-v1','accuracy-confirmation-v2','model-coordination-v1','entry-hardening-v1']:
        for path in (root/name).rglob('protocol.json'):
            prior.update(c.get('text') for c in json.loads(path.read_text(encoding='utf-8')).get('cases',[]) if isinstance(c,dict))
    if prior&{c['text'] for c in cases}:raise ValueError('OLD_EXACT_EXPRESSION')
    if len(cases)!=60 or len({c['text'] for c in cases})!=60:raise ValueError('CASE_COUNT')
    out.mkdir(parents=True,exist_ok=False);(out/'source').mkdir();hashes={}
    for name in SOURCES:
        source=Path(__file__).with_name(name);shutil.copy2(source,out/'source'/name)
        hashes[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    rng=random.Random(972443);trials=[]
    for repeat in range(3):
        block=list(range(60));rng.shuffle(block);trials.extend(dict(index=i,repeat=repeat) for i in block)
    protocol=dict(cases=cases,trials=trials,sourceHashes=hashes,catalog=base,catalogSha256=digest(base),
        model=MODEL,serviceTier='default',sharedBudgetSeconds=8,retries=0,maxCallsThisPhase=180,
        authorizationMaxCalls=200,authorizationCny=20,internalMaxUsd=2,cnyPerUsdGuard=10,
        originalES1FullGateNotClaimed=True,selectionOnly=True,syntheticCatalog=False)
    write(out/'protocol.json',protocol)
    (out/'protocol.sha256').write_text(hashlib.sha256((out/'protocol.json').read_bytes()).hexdigest(),encoding='ascii')
    return protocol


def run(out):
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'));verify_protocol(out,protocol)
    from named_language_evaluation import catalog
    from win_credentials import read_key
    if digest(catalog('R5CW134LLBZ'))!=protocol['catalogSha256']:raise ValueError('LIVE_CATALOG_CHANGED')
    key=read_key()  # Do not log, copy to the protocol or persist this credential.
    ledger=PaidBudget(out/'paid-ledger.json');os.environ['OPENAI_API_KEY']=key
    rows=[];fatal=0
    def transport(body,timeout):return ledger.call(body,timeout,gpt_remote)
    try:
        (out/'trials').mkdir(exist_ok=False)
        for index,trial in enumerate(protocol['trials']):
            folder=out/'trials'/f'{index:03d}';folder.mkdir()
            case=protocol['cases'][trial['index']]
            row=measure('G',case,folder,transport=transport);row['repeat']=trial['repeat'];adjudicate(row)
            rows.append(row);write(folder/'row.json',row);write(out/'results.json',rows);write(out/'summary.json',summary(rows))
            print(json.dumps(dict(n=len(rows),case=case['caseId'],correct=row['correct'],ms=row['ms'],failure=row['failureClass'],error=row.get('error'))),flush=True)
            error=row.get('error','');fatal=fatal+1 if error in ['HTTP_401','HTTP_402','HTTP_403','HTTP_404','HTTP_429'] else 0
            if row['unsafeSuggestion'] or fatal>=3 or error.startswith('PAID_') or sum(not r['available'] for r in rows)>3:
                write(out/'stopped.json',dict(completed=len(rows),reason='UNSAFE' if row['unsafeSuggestion'] else error or 'AVAILABILITY_GATE_UNREACHABLE'))
                break
        verify_protocol(out,protocol)
    finally:
        os.environ.pop('OPENAI_API_KEY',None)
        unchanged=digest(catalog('R5CW134LLBZ'))==protocol['catalogSha256']
        write(out/'preservation.json',dict(actualCatalogUnchanged=unchanged,androidTargetInputs=0))
    return summary(rows)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['freeze','run']);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.mode=='freeze':
        from named_language_evaluation import catalog
        freeze(args.output,catalog('R5CW134LLBZ'));print('Frozen 60 expressions / 180 trials, actual five-skill catalog. No paid calls.')
    else:print(json.dumps(run(args.output),ensure_ascii=True))
