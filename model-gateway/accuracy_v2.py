"""Fresh G/H2 confirmation with one shared deadline; never operates the phone."""
import argparse
import copy
import hashlib
import json
import os
import random
import shutil
import statistics
from pathlib import Path
import time
import model_coordination as bench
from accuracy_confirmation import build_cases,adjudicate,verify_protocol,SOURCES
from accuracy_v2_cases import SPECS
from selection_deadline import SelectionBudget,select_bounded
from compiler import ModelError
from workflow_experiment import write

SNAPSHOT=list(dict.fromkeys(SOURCES+['selection_accuracy.py','selection_deadline.py',
    'deadline_remote.py','accuracy_v2_cases.py','accuracy_v2.py']))


def cases_for(base):
    variants={c['variant']:c['skills'] for c in build_cases(base)}
    identities={tuple(s['finalGoals']):s['id'] for s in variants['near']}
    roles={k:identities[v] for k,v in dict(reading=(1,60,1,1),bright=(1,80,1,3),lamp=(1,60,None,None),
        fan=(None,None,1,1),hundred=(1,100,1,1),near=(1,80,1,1)).items()}
    return [dict(caseId=k+'-'+lang,conceptId=k,category=category,variant=variant,language=lang,text=text,
        expected=roles[target] if target else None,skills=copy.deepcopy(variants[variant]))
        for k,category,variant,target,zh,en in SPECS for lang,text in [('zh',zh),('en',en)]]


def measure(strategy,case,folder=None,transport=None,budget=None):
    started=time.perf_counter();budget=budget or SelectionBudget(8,max_calls=1 if strategy=='G' else 2)
    row=dict(strategy=strategy,case=case)
    try:
        result=select_bounded(strategy,case['text'],case['skills'],budget,transport,transport)
        row.update(available=True,selection=result)
    except (ModelError,ValueError,KeyError,TypeError,RuntimeError) as error:
        row.update(available=False,error=str(error) if isinstance(error,ModelError) else type(error).__name__)
    calls=[]
    for index,entry in enumerate(budget.calls):
        record={k:v for k,v in entry.items() if k not in ('request','response')}
        if folder is not None:
            write(folder/f'request-{index+1}.json',entry['request'])
            if 'response' in entry:write(folder/f'response-{index+1}.json',entry['response'])
        response=entry.get('response',{})
        usage=response if entry['provider']=='GPT' else response.get('usage',{})
        record.update(inputTokens=usage.get('input_tokens'),outputTokens=usage.get('output_tokens'),
            model=response.get('returned_model',response.get('model')))
        calls.append(record)
    row.update(ms=round((time.perf_counter()-started)*1000,4),remoteCalls=len(calls),calls=calls,
        inputTokens=sum(c['inputTokens'] or 0 for c in calls),outputTokens=sum(c['outputTokens'] or 0 for c in calls),
        route='review' if len(calls)==2 else 'remote' if calls else 'local',sharedBudgetSeconds=8)
    if len(calls)>(1 if strategy=='G' else 2):raise ValueError('PER_REQUEST_CAP')
    return adjudicate(row)


def summarize(rows,protocol):
    result=dict(planned=len(protocol['trials']),completed=len(rows),notRun=len(protocol['trials'])-len(rows),
        expressions=len(protocol['cases']),intentClusters=30,selectionOnly=True,gatePassed=False)
    for strategy in ['G','H2']:
        data=[r for r in rows if r['strategy']==strategy];stats=bench.group(data)
        stats['language']={k:bench.group([r for r in data if r['case']['language']==k]) for k in ['zh','en']}
        stats['categories']={k:bench.group([r for r in data if r['case']['category']==k]) for k in sorted({c['category'] for c in protocol['cases']})}
        stats['gptReviews']=sum(r['remoteCalls']==2 for r in data)
        stats['consistentExpressions']=sum(len(v)==3 and all(r['available'] for r in v) and
            len({(r['selection']['status'],r['selection']['skill_id']) for r in v})==1
            for v in [[r for r in data if r['case']['caseId']==c['caseId']] for c in protocol['cases']])
        result[strategy]=stats
    g,h=result['G'],result['H2'];recall=lambda s:s['positiveN'] and s['positiveCorrect']/s['positiveN']>=.95
    result['gatePassed']=result['notRun']==0 and h['unsafeSuggestions']==0 and recall(h) and \
        all(recall(v) for v in h['language'].values()) and h['positiveCorrect']>=g['positiveCorrect'] and h['errors']<=g['errors']
    return result


def preservation():
    from named_journey_device import prefs
    values=prefs('R5CW134LLBZ')
    digest=lambda data:hashlib.sha256(json.dumps(data,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    root=Path(__file__).parents[1]
    return dict(library=digest(values.get('library')),approved=digest(values.get('approved')),
        recordedPrefs=digest(values),androidJava={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (root/'android-agent-probe').rglob('*.java')})


def freeze(out):
    from named_language_evaluation import catalog
    data=cases_for(catalog('R5CW134LLBZ'));prior=set()
    for path in [out.parents[1]/'accuracy-confirmation-v1/confirmation/protocol.json',
                 out.parents[1]/'accuracy-confirmation-v1/repair-pilot/protocol.json',
                 out.parents[1]/'model-coordination-v1/confirmation/protocol.json']:
        prior.update(c['text'] for c in json.loads(path.read_text(encoding='utf-8'))['cases'])
    if {c['text'] for c in data}&prior:raise ValueError('OLD_EXACT_TEXT')
    assert len(data)==60 and sum(c['expected'] is not None for c in data)==30
    assert len({c['text'] for c in data})==60
    out.mkdir(parents=True,exist_ok=False);(out/'source').mkdir();hashes={};rng=random.Random(1069284);trials=[]
    for repeat in range(3):
        block=list(range(60));rng.shuffle(block)
        for index in block:
            order=['G','H2'];rng.shuffle(order)
            trials.extend(dict(index=index,repeat=repeat,strategy=s) for s in order)
    for name in SNAPSHOT:
        p=Path(__file__).with_name(name);shutil.copy2(p,out/'source'/name);hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    protocol=dict(cases=data,trials=trials,sourceHashes=hashes,maxRemoteCalls=540,batchSize=60,
        threshold=.90,sharedBudgetSeconds=8,retries=0,selectionOnly=True,
        authorLabelledNotIndependentHumanGold=True,syntheticCatalogsNotExecutable=True,
        criteria='zero unsafe suggestions, recall >=95% overall and per language, positives/errors not worse than G')
    write(out/'protocol.json',protocol)
    (out/'protocol.sha256').write_text(hashlib.sha256((out/'protocol.json').read_bytes()).hexdigest(),encoding='ascii')
    write(out/'preservation-before.json',preservation())
    return protocol


def run_batch(out,measure_fn=None):
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'));verify_protocol(out,protocol)
    if (out/'stopped.json').exists():raise ValueError('STOPPED_REQUIRES_REVIEW')
    path=out/'results.json';rows=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    trials=out/'trials';trials.mkdir(exist_ok=True)
    if len(list(trials.iterdir()))!=len(rows):raise ValueError('INCOMPLETE_TRIAL_REQUIRES_REVIEW')
    for index,row in enumerate(rows):
        trial=protocol['trials'][index]
        if json.loads((trials/f'{index:03d}-{row["strategy"]}/row.json').read_text(encoding='utf-8'))!=row:
            raise ValueError('ROW_CHANGED')
        if row['case']!=protocol['cases'][trial['index']] or row['repeat']!=trial['repeat'] or row['strategy']!=trial['strategy']:
            raise ValueError('TRIAL_CHANGED')
    if measure_fn is None:
        from win_credentials import read_key
        os.environ['OPENAI_API_KEY']=read_key()
    fatal=0
    for row in reversed(rows):
        if row.get('error') not in ['HTTP_401','HTTP_402','HTTP_403','HTTP_429']:break
        fatal+=1
    for index in range(len(rows),min(len(rows)+protocol['batchSize'],len(protocol['trials']))):
        trial=protocol['trials'][index];strategy=trial['strategy'];case=protocol['cases'][trial['index']]
        if sum(r['remoteCalls'] for r in rows)+(1 if strategy=='G' else 2)>protocol['maxRemoteCalls']:raise ValueError('CALL_CAP')
        folder=trials/f'{index:03d}-{strategy}';folder.mkdir(exist_ok=False)
        row=(measure_fn or measure)(strategy,case,folder);row['repeat']=trial['repeat'];rows.append(row)
        write(folder/'row.json',row);write(path,rows);write(out/'summary.json',summarize(rows,protocol))
        print(json.dumps(dict(n=len(rows),strategy=strategy,case=case['caseId'],correct=row['correct'],
            failure=row['failureClass'],ms=row['ms'],calls=row['remoteCalls'],error=row.get('error'))),flush=True)
        fatal=fatal+1 if row.get('error') in ['HTTP_401','HTTP_402','HTTP_403','HTTP_429'] else 0
        if fatal>=3:write(out/'stopped.json',dict(reason='ACCOUNT_ERRORS',completed=len(rows)));break
    return summarize(rows,protocol)


def analyse(out):
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'));verify_protocol(out,protocol)
    rows=json.loads((out/'results.json').read_text(encoding='utf-8'));pairs={};clusters={};different=[]
    for row in rows:pairs.setdefault((row['case']['caseId'],row['repeat']),{})[row['strategy']]=row
    for (key,repeat),pair in pairs.items():
        if set(pair)=={'G','H2'}:
            delta=int(pair['H2']['correct'])-int(pair['G']['correct'])
            clusters.setdefault(pair['G']['case']['conceptId'],[]).append(delta)
            if delta:different.append(dict(caseId=key,repeat=repeat,delta=delta))
    means=[statistics.mean(v) for v in clusters.values()];rng=random.Random(349810)
    draws=[statistics.mean(rng.choices(means,k=len(means))) for _ in range(2000)] if means else []
    result=dict(summary=summarize(rows,protocol),paired=dict(intentClusters=len(means),
        difference=statistics.mean(means) if means else None,
        descriptiveClusterBootstrap95=[bench.percentile(draws,.025),bench.percentile(draws,.975)],discordant=different),
        failures=[dict(caseId=r['case']['caseId'],strategy=r['strategy'],repeat=r['repeat'],
            failureClass=r['failureClass'],selection=r.get('selection'),error=r.get('error')) for r in rows if not r['correct']])
    write(out/'analysis.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','run','analyse','preserve']);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='freeze':freeze(a.output);print('Frozen new 60 bilingual expressions; zero API calls.')
    elif a.mode=='run':print(json.dumps(run_batch(a.output),ensure_ascii=False))
    elif a.mode=='analyse':print(json.dumps(analyse(a.output)['summary'],ensure_ascii=False))
    else:
        before=json.loads((a.output/'preservation-before.json').read_text(encoding='utf-8'));after=preservation()
        write(a.output/'preservation-after.json',dict(unchanged=before==after,before=before,after=after));print('Protected state unchanged:',before==after)
