"""GPT-only prospective confirmation; selection only, no target-App execution."""
import argparse
import hashlib
import json
import os
import random
import shutil
from pathlib import Path
from entry_confirmation_cases import SPECS
from accuracy_confirmation import build_cases,verify_protocol,adjudicate
from accuracy_v2 import measure
from skill_selection import validate_catalog
from workflow_experiment import write
import model_coordination as bench

SOURCES=['entry_confirmation.py','entry_confirmation_cases.py','skill_selection.py','catalog_uniqueness.py',
    'selection_deadline.py','selection_accuracy.py','selection_routing.py','jev_selection.py','compiler.py',
    'contracts.py','deadline_remote.py','accuracy_v2.py','accuracy_v2_cases.py','accuracy_confirmation.py','accuracy_cases.py','model_coordination.py']

def cases_for(base):
    variants={c['variant']:c['skills'] for c in build_cases(base)}
    ids={tuple(s['finalGoals']):s['id'] for s in variants['near']}
    roles=dict(reading=(1,60,1,1),bright=(1,80,1,3),lamp=(1,60,None,None),fan=(None,None,1,1),hundred=(1,100,1,1),near=(1,80,1,1))
    return [dict(caseId=key+'-'+lang,conceptId=key,category=category,variant=variant,language=lang,text=text,
        expected=ids[roles[target]] if target else None,skills=variants[variant])
        for key,category,variant,target,zh,en in SPECS for lang,text in [('zh',zh),('en',en)]]

def freeze(out,base):
    cases=cases_for(validate_catalog(base));prior=set()
    root=Path(__file__).parents[1]/'output'
    for name in ['accuracy-confirmation-v1','accuracy-confirmation-v2','model-coordination-v1']:
        for p in (root/name).rglob('protocol.json'):
            prior.update(c.get('text') for c in json.loads(p.read_text(encoding='utf-8')).get('cases',[]) if isinstance(c,dict))
    if prior&{c['text'] for c in cases}:raise ValueError('OLD_EXACT_EXPRESSION')
    if len(cases)!=60 or sum(c['expected'] is not None for c in cases)!=30:raise ValueError('CASE_BALANCE')
    out.mkdir(parents=True,exist_ok=False);(out/'source').mkdir();hashes={}
    for name in SOURCES:
        p=Path(__file__).with_name(name);shutil.copy2(p,out/'source'/name);hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    rng=random.Random(381247);trials=[]
    for repeat in range(3):
        block=list(range(60));rng.shuffle(block)
        trials.extend(dict(index=i,repeat=repeat,strategy='G') for i in block)
    protocol=dict(cases=cases,trials=trials,sourceHashes=hashes,sharedBudgetSeconds=8,retries=0,maxRemoteCalls=180,
        selectionOnly=True,authorLabelledNotIndependentHumanGold=True,syntheticCatalogsNotExecutable=True,
        gate=dict(positiveMin=86,positiveN=90,positiveLanguageMin=43,positiveLanguageN=45,unsafeMax=0))
    write(out/'protocol.json',protocol)
    (out/'protocol.sha256').write_text(hashlib.sha256((out/'protocol.json').read_bytes()).hexdigest(),encoding='ascii')
    return protocol

def summarize(rows,protocol):
    stats=bench.group(rows)
    stats.update(planned=180,completed=len(rows),selectionOnly=True,
        language={lang:bench.group([r for r in rows if r['case']['language']==lang]) for lang in ['zh','en']},
        byCategory={cat:bench.group([r for r in rows if r['case']['category']==cat]) for cat in sorted({c['category'] for c in protocol['cases']})},
        failureClasses={name:sum(r['failureClass']==name for r in rows) for name in ['none','availability','false_invoke','wrong_id','valid_abstention']})
    stats['gatePassed']=len(rows)==180 and stats['positiveCorrect']>=86 and stats['unsafeSuggestions']==0 and \
        all(stats['language'][lang]['positiveCorrect']>=43 for lang in ['zh','en'])
    stats['consistentExpressions']=sum(len(v)==3 and all(r['available'] for r in v) and len({(r['selection']['status'],r['selection']['skill_id']) for r in v})==1
        for v in [[r for r in rows if r['case']['caseId']==c['caseId']] for c in protocol['cases']])
    return stats

def run(out,limit=60,measurement=measure):
    if type(limit) is not int or not 1<=limit<=180:raise ValueError('INVALID_BATCH_LIMIT')
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'));verify_protocol(out,protocol)
    if (out/'stopped.json').exists():raise ValueError('STOPPED_REQUIRES_REVIEW')
    path=out/'results.json';rows=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    trials=out/'trials';trials.mkdir(exist_ok=True)
    if len(list(trials.iterdir()))!=len(rows):raise ValueError('INCOMPLETE_TRIAL')
    for i,row in enumerate(rows):
        trial=protocol['trials'][i]
        if row['case']!=protocol['cases'][trial['index']] or row['repeat']!=trial['repeat']:raise ValueError('ROW_CHANGED')
        if json.loads((trials/f'{i:03d}/row.json').read_text(encoding='utf-8'))!=row:raise ValueError('ROW_CHANGED')
    if measurement is measure:
        from win_credentials import read_key
        os.environ['OPENAI_API_KEY']=read_key()
    fatal=0
    for row in reversed(rows):
        if row.get('error') not in ['HTTP_401','HTTP_402','HTTP_403','HTTP_429']:break
        fatal+=1
    for i in range(len(rows),min(len(rows)+limit,180)):
        trial=protocol['trials'][i];folder=trials/f'{i:03d}';folder.mkdir(exist_ok=False)
        row=measurement('G',protocol['cases'][trial['index']],folder);row['repeat']=trial['repeat'];adjudicate(row)
        if row['remoteCalls']>1:raise ValueError('CALL_CAP')
        rows.append(row);write(folder/'row.json',row);write(path,rows);write(out/'summary.json',summarize(rows,protocol))
        print(json.dumps(dict(n=len(rows),case=row['case']['caseId'],correct=row['correct'],failure=row['failureClass'],ms=row['ms']),ensure_ascii=True),flush=True)
        fatal=fatal+1 if row.get('error') in ['HTTP_401','HTTP_402','HTTP_403','HTTP_429'] else 0
        if fatal>=3 or row['unsafeSuggestion']:
            write(out/'stopped.json',dict(reason='UNSAFE_OR_ACCOUNT',completed=len(rows)));break
    return summarize(rows,protocol)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','run','summary']);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int,default=60);a=p.parse_args()
    if a.mode=='freeze':
        from named_language_evaluation import catalog
        print('Frozen '+str(len(freeze(a.output,catalog('R5CW134LLBZ'))['cases']))+' expressions; no model calls.')
    elif a.mode=='run':print(json.dumps(run(a.output,a.limit)))
    else:print(json.dumps(summarize(json.loads((a.output/'results.json').read_text(encoding='utf-8')),json.loads((a.output/'protocol.json').read_text(encoding='utf-8')))))
