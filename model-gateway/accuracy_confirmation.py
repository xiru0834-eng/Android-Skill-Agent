"""Frozen G/F selection-only confirmation. No phone inputs, retry or deployment."""
import argparse
import copy
import hashlib
import json
import os
import random
import shutil
import statistics
from pathlib import Path
import model_coordination as bench
from accuracy_cases import SPECS
from skill_selection import validate_catalog
from start_teaching_bridge import resolve_selector
from workflow_experiment import write

SOURCES=list(dict.fromkeys(bench.SOURCES+['accuracy_confirmation.py','accuracy_cases.py',
    'start_teaching_bridge.py','win_credentials.py','jev_selection_benchmark.py',
    'workflow_experiment.py','named_language_evaluation.py']))


def build_cases(base):
    base=copy.deepcopy(validate_catalog(base));ids={tuple(s['finalGoals']):s['id'] for s in base}
    roles={k:ids[g] for k,g in dict(reading=(1,60,1,1),bright=(1,80,1,3),
        lamp=(1,60,None,None),fan=(None,None,1,1),hundred=(1,100,1,1)).items()}
    roles['near']=hashlib.sha256(b'accuracy-holdout-soft-low').hexdigest()
    extra=dict(id=roles['near'],name='柔光80低档 / Soft80Low',goal='Lamp ON at 80%, fan ON at low speed.',finalGoals=[1,80,1,1])
    duplicate=dict(id=hashlib.sha256(b'accuracy-holdout-reading-copy').hexdigest(),
        name='安静阅读 / QuietReading',goal='Same target values, a separate saved identity.',finalGoals=[1,60,1,1])
    variants=dict(base=base,reversed=list(reversed(base)),near=base+[extra],duplicate=base+[duplicate],
        removed=[s for s in base if s['id']!=roles['reading']])
    rows=[]
    for concept,category,variant,target,zh,en in SPECS:
        for language,text in [('zh',zh),('en',en)]:
            rows.append(dict(caseId=concept+'-'+language,conceptId=concept,category=category,
                variant=variant,language=language,text=text,expected=roles[target] if target else None,
                acceptableStatuses=['invoke'] if target else ['clarify','reject'],
                labelBasis='Exact immutable targets or unique named skill' if target else 'No immediate permitted unique immutable workflow',
                skills=copy.deepcopy(validate_catalog(variants[variant]))))
    return rows


def adjudicate(row):
    bench.score(row)
    s=row.get('selection',{});expected=row['case']['expected']
    row['failureClass']='none' if row['correct'] else ('availability' if not row['available'] else
        'false_invoke' if expected is None and s.get('status')=='invoke' else
        'wrong_id' if s.get('status')=='invoke' else 'valid_abstention')
    return row


def aggregate(rows,protocol):
    result=dict(planned=len(protocol['trials']),completed=len(rows),notRun=len(protocol['trials'])-len(rows),
        distinctInstructions=len(protocol['cases']),intentClusters=30,gatePassed=False)
    for strategy in ['G','F']:
        data=[r for r in rows if r['strategy']==strategy];stats=bench.group(data)
        stats['language']={k:bench.group([r for r in data if r['case']['language']==k]) for k in ['zh','en']}
        stats['categories']={k:bench.group([r for r in data if r['case']['category']==k]) for k in sorted({c['category'] for c in protocol['cases']})}
        stats['routes']={k:bench.group([r for r in data if r['route']==k]) for k in ['literal-name','remote','local-error']}
        buckets={c['caseId']:[r for r in data if r['case']['caseId']==c['caseId']] for c in protocol['cases']}
        stats['consistentInstructions']=sum(len(v)==3 and all(r['available'] for r in v) and
            len({(r['selection']['status'],r['selection']['skill_id']) for r in v})==1 for v in buckets.values())
        result[strategy]=stats
    candidate=result['F'];baseline=result['G']
    recall=lambda s:s['positiveN']>0 and s['positiveCorrect']/s['positiveN']>=.95
    result['gatePassed']=result['notRun']==0 and candidate['unsafeSuggestions']==0 and recall(candidate) and \
        all(recall(v) for v in candidate['language'].values()) and candidate['positiveCorrect']>=baseline['positiveCorrect'] and \
        candidate['errors']<=baseline['errors']
    return result


def freeze(out,skills):
    out=Path(out);out.mkdir(parents=True,exist_ok=False);(out/'source').mkdir()
    cases=build_cases(skills);trials=[];rng=random.Random(817405)
    for repeat in range(3):
        block=list(range(60));rng.shuffle(block)
        for index in block:
            order=['G','F'];rng.shuffle(order)
            for strategy in order:trials.append(dict(index=index,repeat=repeat,strategy=strategy))
    hashes={}
    for name in SOURCES:
        source=Path(__file__).with_name(name);shutil.copy2(source,out/'source'/name)
        hashes[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    protocol=dict(cases=cases,trials=trials,sourceHashes=hashes,maxRemoteCalls=360,batchSize=60,
        threshold=.90,timeoutSeconds=45,retries=0,selectionOnly=True,syntheticCatalogsNotExecutable=True,
        authorLabelledNotIndependentHumanGold=True,nonInvokePolicy='clarify and reject both safe; exact status separately recorded')
    write(out/'protocol.json',protocol)
    (out/'protocol.sha256').write_text(hashlib.sha256((out/'protocol.json').read_bytes()).hexdigest(),encoding='ascii')
    return protocol


def verify_protocol(out,protocol):
    saved=json.loads((out/'protocol.json').read_text(encoding='utf-8'))
    if protocol!=saved or hashlib.sha256((out/'protocol.json').read_bytes()).hexdigest()!=(out/'protocol.sha256').read_text():
        raise ValueError('FROZEN_LABELS_CHANGED')
    for name,digest in protocol['sourceHashes'].items():
        if any(hashlib.sha256(p.read_bytes()).hexdigest()!=digest for p in [Path(__file__).with_name(name),out/'source'/name]):
            raise ValueError('FROZEN_SOURCE_CHANGED')


def live_measure(strategy,case,folder):
    def capture(body):
        write(folder/'request.json',body)
        response=(bench.gpt_remote if strategy=='G' else bench.jev_remote)(body)
        # Never persist a credential echo, including an unexpected GPT reply.
        response=json.loads(json.dumps(response).replace(os.environ['OPENAI_API_KEY'],'[REDACTED]'))
        write(folder/'response.json',response)
        return response
    return bench.measure(strategy,case['text'],case['skills'],transport=capture,
        selector=resolve_selector('gpt' if strategy=='G' else 'routed'))


def run_batch(out,measure_fn=None):
    out=Path(out);protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'));verify_protocol(out,protocol)
    if (out/'stopped.json').exists():raise ValueError('STOPPED_BATCH_REQUIRES_REVIEW')
    path=out/'results.json';rows=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
    trials=out/'trials';trials.mkdir(exist_ok=True)
    if len(list(trials.iterdir()))!=len(rows):raise ValueError('INCOMPLETE_TRIAL_REQUIRES_REVIEW')
    for index,row in enumerate(rows):
        if json.loads((trials/f'{index:03d}-{row["strategy"]}'/'row.json').read_text(encoding='utf-8'))!=row:
            raise ValueError('SAVED_ROW_CHANGED')
        trial=protocol['trials'][index]
        if row['case']!=protocol['cases'][trial['index']] or row['repeat']!=trial['repeat'] or row['strategy']!=trial['strategy']:
            raise ValueError('SAVED_TRIAL_MISMATCH')
    if measure_fn is None:
        from win_credentials import read_key
        os.environ['OPENAI_API_KEY']=read_key()
    fatal=0;start=len(rows)
    for old in reversed(rows):
        if old.get('error') not in ['HTTP_401','HTTP_402','HTTP_403','HTTP_429']:break
        fatal+=1
    for index in range(start,min(start+protocol['batchSize'],len(protocol['trials']))):
        if sum(r['remoteCalls'] for r in rows)>=protocol['maxRemoteCalls']:raise ValueError('CALL_CAP')
        trial=protocol['trials'][index];case=protocol['cases'][trial['index']];strategy=trial['strategy']
        folder=trials/f'{index:03d}-{strategy}';folder.mkdir(exist_ok=False)
        row=(measure_fn or live_measure)(strategy,case,folder)
        row.update(case=case,repeat=trial['repeat']);adjudicate(row)
        if row['remoteCalls']>1:raise ValueError('UNEXPECTED_MULTIPLE_CALLS')
        rows.append(row);write(folder/'row.json',row);write(path,rows)
        summary=aggregate(rows,protocol);write(out/'summary.json',summary)
        print(json.dumps(dict(n=len(rows),strategy=strategy,case=case['caseId'],correct=row['correct'],
            failure=row['failureClass'],ms=row['ms'],calls=row['remoteCalls'],error=row.get('error'))),flush=True)
        fatal=fatal+1 if row.get('error') in ['HTTP_401','HTTP_402','HTTP_403','HTTP_429'] else 0
        if fatal>=3:
            write(out/'stopped.json',dict(reason='CONSECUTIVE_ACCOUNT_ERRORS',completed=len(rows)));break
    return aggregate(rows,protocol)


def analyse(out):
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'));verify_protocol(out,protocol)
    rows=json.loads((out/'results.json').read_text(encoding='utf-8'))
    for row in rows:adjudicate(row)
    pairs={}
    for row in rows:pairs.setdefault((row['case']['caseId'],row['repeat']),{})[row['strategy']]=row
    clusters={};disagree=[]
    for (case_id,repeat),pair in pairs.items():
        if set(pair)=={'G','F'}:
            a,b=pair['G'],pair['F'];delta=int(b['correct'])-int(a['correct'])
            clusters.setdefault(a['case']['conceptId'],[]).append(delta)
            if delta:disagree.append(dict(caseId=case_id,repeat=repeat,gpt=a['correct'],candidate=b['correct']))
    means=[statistics.mean(v) for v in clusters.values()];rng=random.Random(374157)
    draws=[statistics.mean(rng.choices(means,k=len(means))) for _ in range(2000)] if means else []
    result=dict(summary=aggregate(rows,protocol),paired=dict(intentClusters=len(means),
        difference=statistics.mean(means) if means else None,
        clusterBootstrap95=[bench.percentile(draws,.025),bench.percentile(draws,.975)],discordant=disagree),
        failures=[dict(caseId=r['case']['caseId'],strategy=r['strategy'],repeat=r['repeat'],
            failureClass=r['failureClass'],selection=r.get('selection'),modelAnswer=r.get('modelAnswer'),error=r.get('error'))
            for r in rows if not r['correct']])
    write(out/'analysis.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','run','analyse']);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='freeze':
        from named_language_evaluation import catalog
        freeze(a.output,catalog('R5CW134LLBZ'));print('Frozen 60 new bilingual instructions; no API calls or phone inputs.')
    elif a.mode=='run':print(json.dumps(run_batch(a.output),ensure_ascii=False))
    else:print(json.dumps(analyse(a.output)['summary'],ensure_ascii=False))
