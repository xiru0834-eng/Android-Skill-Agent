"""Independent small repair ablation, selection-only; no product activation."""
import argparse
import copy
import hashlib
import json
import os
import random
import shutil
import time
from pathlib import Path
import model_coordination as bench
from accuracy_confirmation import build_cases,adjudicate,verify_protocol,SOURCES
from selection_accuracy import select_accuracy
from start_teaching_bridge import resolve_selector
from workflow_experiment import write
from win_credentials import read_key
from compiler import MODEL,ModelError

STRATEGIES=['G','F','A','H']
SNAPSHOT=list(dict.fromkeys(SOURCES+['selection_accuracy.py','accuracy_repair_pilot.py']))


def pilot_cases(base):
    variants={c['variant']:c['skills'] for c in build_cases(base)}
    ids={tuple(s['finalGoals']):s['id'] for s in variants['near']}
    specs=[
      ('missing-name','removed',None,'请运行已保存的阅读60流程，不接受其他模式替代。','Use the saved Reading60 routine immediately; do not substitute another workflow.'),
      ('known-name','base',ids[(1,60,1,1)],'请执行保存的阅读60流程，所有设置都保持技能里的值。','Use the saved Reading60 workflow with every stored setting unchanged.'),
      ('natural-name','base',ids[(1,60,None,None)],'我想现在用只灯60这条以前保存的流程，不改其中设置。','The existing LampOnly60 routine is the one to use; follow it now without changing settings.'),
      ('near-goals','near',ids[(1,80,1,1)],'阅读灯开启且亮度80%，风扇开启且低速；不要用风扇高速那套。','Please put the lamp ON at eighty percent and the fan ON at low, rather than using the high-speed combination.'),
      ('scope-fan','base',ids[(None,None,1,1)],'风扇设为开启和低档，灯的亮度与开关均保持执行前状态。','Put the fan in the ON, low-speed state while retaining the lamp current power and brightness.'),
      ('no-action','base',None,'请介绍只灯60如何工作，但不允许启动。','Tell me how LampOnly60 works; do not activate it.'),
      ('modified','base',None,'阅读60这条技能我要改到灯亮度20%再运行。','Before running Reading60, replace its saved brightness with twenty percent.'),
      ('equivalent','duplicate',None,'把灯设置为开启60%，风扇开启低档，两个同目标流程任选一个。','Turn lamp ON at sixty percent and fan ON at low; choose either of the equivalent routines.')]
    return [dict(caseId=k+'-'+language,conceptId=k,category=k,variant=variant,language=language,text=text,
        expected=expected,acceptableStatuses=['invoke'] if expected else ['clarify','reject'],
        skills=copy.deepcopy(variants[variant])) for k,variant,expected,zh,en in specs for language,text in [('zh',zh),('en',en)]]


def measure(strategy,case,folder,transport=None):
    started=time.perf_counter();calls=[]
    def tracked(body):
        record=dict(provider='GPT' if body['model']==MODEL else 'Jev',requestBytes=len(json.dumps(body).encode()))
        calls.append(record)
        if folder is not None:write(folder/f'request-{len(calls)}.json',body)
        response=(transport or (bench.gpt_remote if body['model']==MODEL else bench.jev_remote))(body)
        key=os.environ.get('OPENAI_API_KEY')
        if key:response=json.loads(json.dumps(response).replace(key,'[REDACTED]'))
        if folder is not None:write(folder/f'response-{len(calls)}.json',response)
        usage=response if record['provider']=='GPT' else response.get('usage',{})
        record.update(inputTokens=usage.get('input_tokens'),outputTokens=usage.get('output_tokens'),
            model=response.get('returned_model',response.get('model')))
        return response
    row=dict(strategy=strategy,case=case)
    try:
        selector=resolve_selector('gpt' if strategy=='G' else 'routed')
        result=selector(case['text'],case['skills'],tracked) if strategy in ['G','F'] else \
            select_accuracy(case['text'],case['skills'],tracked,tracked,review=strategy=='H')
        row.update(available=True,selection=result)
    except (ModelError,ValueError,KeyError,TypeError) as exc:
        row.update(available=False,error=str(exc) if isinstance(exc,ModelError) else type(exc).__name__)
    row.update(ms=round((time.perf_counter()-started)*1000,4),remoteCalls=len(calls),calls=calls,
        inputTokens=sum(c.get('inputTokens') or 0 for c in calls),outputTokens=sum(c.get('outputTokens') or 0 for c in calls),
        route='two-model-review' if len(calls)==2 else 'remote' if calls else 'local')
    if len(calls)>2:raise ValueError('PER_REQUEST_CAP')
    return adjudicate(row)


def summarize(rows):
    result=dict(planned=128,completed=len(rows),notRun=128-len(rows),distinctExpressions=16,intentClusters=8,
        developmentRepairPilot=True,phoneExecution=False)
    for strategy in STRATEGIES:
        data=[r for r in rows if r['strategy']==strategy];stats=bench.group(data)
        stats['gptReviews']=sum(r['remoteCalls']==2 for r in data)
        stats['language']={k:bench.group([r for r in data if r['case']['language']==k]) for k in ['zh','en']}
        result[strategy]=stats
    return result


def freeze(out):
    from named_language_evaluation import catalog
    out.mkdir(parents=True,exist_ok=False);(out/'source').mkdir();cases=pilot_cases(catalog('R5CW134LLBZ'))
    prior=json.loads((out.parent/'confirmation/protocol.json').read_text(encoding='utf-8'))
    assert not {c['text'] for c in cases}&{c['text'] for c in prior['cases']}
    rng=random.Random(925061);trials=[];hashes={}
    for repeat in range(2):
        block=list(range(16));rng.shuffle(block)
        for index in block:
            order=STRATEGIES.copy();rng.shuffle(order)
            trials.extend(dict(index=index,repeat=repeat,strategy=s) for s in order)
    for name in SNAPSHOT:
        source=Path(__file__).with_name(name);shutil.copy2(source,out/'source'/name)
        hashes[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    protocol=dict(cases=cases,trials=trials,sourceHashes=hashes,maxRemoteCalls=160,maxDecisions=128,
        threshold=.90,retries=0,selectionOnly=True,newTexts=True,developmentRepairPilot=True)
    write(out/'protocol.json',protocol)
    (out/'protocol.sha256').write_text(hashlib.sha256((out/'protocol.json').read_bytes()).hexdigest())
    return protocol


def run(out):
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'));verify_protocol(out,protocol)
    (out/'trials').mkdir(exist_ok=False);os.environ['OPENAI_API_KEY']=read_key();rows=[];fatal=0
    for index,trial in enumerate(protocol['trials']):
        if sum(r['remoteCalls'] for r in rows)+2>protocol['maxRemoteCalls']:raise ValueError('CALL_CAP')
        case=protocol['cases'][trial['index']];folder=out/'trials'/f'{index:03d}-{trial["strategy"]}';folder.mkdir()
        row=measure(trial['strategy'],case,folder);row['repeat']=trial['repeat'];rows.append(row)
        write(folder/'row.json',row);write(out/'results.json',rows);write(out/'summary.json',summarize(rows))
        print(json.dumps(dict(n=len(rows),strategy=row['strategy'],case=case['caseId'],correct=row['correct'],
            failure=row['failureClass'],calls=row['remoteCalls'],ms=row['ms'])),flush=True)
        fatal=fatal+1 if row.get('error') in ['HTTP_401','HTTP_402','HTTP_403','HTTP_429'] else 0
        if fatal>=3:write(out/'stopped.json',dict(reason='CONSECUTIVE_ACCOUNT_ERRORS',completed=len(rows)));break
    return summarize(rows)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','run']);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='freeze':freeze(a.output);print('Frozen 16 new expressions; no API calls.')
    else:print(json.dumps(run(a.output),ensure_ascii=False))
