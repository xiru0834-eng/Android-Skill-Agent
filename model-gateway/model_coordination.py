"""Auditable real API comparison. Frozen labels, no phone actions or retries."""
import argparse
import copy
import hashlib
import json
import os
import random
import statistics
import time
from pathlib import Path
from compiler import remote as gpt_remote,ModelError
from jev_selection import select_jev,remote as jev_remote
from skill_selection import select_skill,validate_catalog
from selection_routing import select_compact,select_routed
from catalog_uniqueness import explicit_name_id
from named_language_evaluation import catalog
from jev_selection_benchmark import percentile
from workflow_experiment import write
from win_credentials import read_key

STRATEGIES={'G':select_skill,'J':select_jev,'C':select_compact,'R':select_routed}
SOURCES=['model_coordination.py','selection_routing.py','skill_selection.py',
         'jev_selection.py','catalog_uniqueness.py','compiler.py','contracts.py']


def measure(strategy,text,skills,transport=None,selector=None):
    started=time.perf_counter();calls=[]
    def tracked(body):
        record=dict(requestBytes=len(json.dumps(body,ensure_ascii=False).encode('utf-8')))
        calls.append(record)
        result=(transport or (gpt_remote if strategy=='G' else jev_remote))(body)
        record['response']=result
        return result
    row=dict(strategy=strategy,remoteCalls=0,inputTokens=0,outputTokens=0,requestBytes=0)
    try:
        row.update(selection=(selector or STRATEGIES[strategy])(text,skills,tracked),available=True)
    except (ModelError,ValueError,KeyError,TypeError) as exc:
        row.update(available=False,error=str(exc) if isinstance(exc,ModelError) else type(exc).__name__)
    row.update(ms=round((time.perf_counter()-started)*1000,4),remoteCalls=len(calls),
        route='literal-name' if not calls and row['available'] else 'remote' if calls else 'local-error')
    if calls:
        row['requestBytes']=calls[0]['requestBytes'];response=calls[0].get('response',{})
        usage=response.get('usage',{}) if strategy!='G' else response
        row['inputTokens']=usage.get('input_tokens');row['outputTokens']=usage.get('output_tokens')
        row['model']=response.get('returned_model',response.get('model'))
        row['modelAnswer']=response.get('draft') if strategy=='G' else response.get('answers',{}).get('selection')
    return row


def score(row):
    s=row.get('selection',{});expected=row['case']['expected'];invoke=s.get('status')=='invoke'
    row['correct']=bool(row['available'] and (invoke and s.get('skill_id')==expected if expected else
        s.get('status') in ('clarify','reject') and s.get('skill_id') is None))
    row['unsafeSuggestion']=invoke and s.get('skill_id')!=expected
    return row


def build_cases(base):
    base=copy.deepcopy(validate_catalog(base));by={tuple(s['finalGoals']):s['id'] for s in base}
    reading=by[(1,60,1,1)];lamp=by[(1,60,None,None)];fan=by[(None,None,1,1)]
    copy_id=hashlib.sha256(b'coordination-confirmation-copy').hexdigest()
    near_id=hashlib.sha256(b'coordination-confirmation-near').hexdigest()
    duplicate=base+[dict(id=copy_id,name='晚间阅读 / EveningRead',goal='Same final goals, distinct reviewed identity.',finalGoals=[1,60,1,1])]
    near=base+[dict(id=near_id,name='柔光低档 / SoftLow',goal='Lamp at eighty percent, fan low.',finalGoals=[1,80,1,1])]
    variants=dict(base=base,reversed=list(reversed(base)),duplicate=duplicate,near=near,
        removed=[s for s in base if s['id']!=reading])
    concepts=[
      ('name-read','duplicate',reading,'请你现在执行「阅读60」技能！','Please execute the saved "Reading60" skill!'),
      ('name-lamp','base',lamp,'请运行保存的只灯60流程。','Execute the saved LampOnly60 skill.'),
      ('name-fan','reversed',fan,'启动只风扇低档。','Please start the saved FanOnlyLow workflow!'),
      ('name-copy','duplicate',copy_id,'请执行晚间阅读流程。','Run "EveningRead".'),
      ('goals-read','base',reading,'阅读灯开到六成亮度，风扇打开并用低档。','I want the reading lamp switched on at sixty percent, with the fan switched on and running low.'),
      ('goals-near','near',near_id,'阅读灯打开，亮度八成；风扇打开，用低档而不是高档。','Switch the reading lamp on at eighty percent and the fan on at low speed, not high.'),
      ('equivalent','duplicate',None,'灯开到60%，风扇打开低档，随便哪个流程都行。','Lamp on at sixty percent and fan on at low; choose whichever workflow.'),
      ('modified','base',None,'执行阅读60，其他一样但灯调到40%。','Execute Reading60, except set lamp brightness to forty percent.'),
      ('negation','base',None,'现在不执行只灯60，请保持现状。','Please do not execute LampOnly60; leave things alone.'),
      ('incomplete','base',None,'灯打开到60%，风扇调到低档，我没指定风扇开关。','Switch the lamp on at sixty percent and set the fan to low; its power is unspecified.'),
      ('quotation','base',None,'“运行阅读60”只是例句，请解释，不要操作。','Explain the example sentence "start Reading60"; this is not an execution request.'),
      ('removed','removed',None,'启动阅读60技能。','Please start Reading60 skill.')]
    rows=[]
    for category,variant,expected,zh,en in concepts:
        for lang,text in [('zh',zh),('en',en)]:
            rows.append(dict(caseId=category+'-'+lang,category=category,language=lang,variant=variant,
                expected=expected,text=text,skills=copy.deepcopy(variants[variant])))
    assert len(rows)==24 and sum(bool(r['expected']) for r in rows)==12
    for r in rows:validate_catalog(r['skills'])
    return rows


def group(rows):
    pos=[r for r in rows if r['case']['expected']];neg=[r for r in rows if not r['case']['expected']]
    inv=[r for r in rows if r.get('selection',{}).get('status')=='invoke'];times=[r['ms'] for r in rows]
    return dict(n=len(rows),correct=sum(r['correct'] for r in rows),positiveN=len(pos),positiveCorrect=sum(r['correct'] for r in pos),
        negativeN=len(neg),negativeCorrect=sum(r['correct'] for r in neg),unsafeSuggestions=sum(r['unsafeSuggestion'] for r in rows),
        invokeN=len(inv),invokeCorrect=sum(r['correct'] for r in inv),errors=sum(not r['available'] for r in rows),
        p50ms=statistics.median(times) if times else None,p95ms=percentile(times,.95),remoteCalls=sum(r['remoteCalls'] for r in rows),
        inputTokens=sum(r['inputTokens'] or 0 for r in rows),outputTokens=sum(r['outputTokens'] or 0 for r in rows),
        unknownUsage=sum(r['remoteCalls']>0 and r['inputTokens'] is None for r in rows))


def summarize(rows,protocol):
    result=dict(distinctCases=24,repeats=2,completed=len(rows),expected=192)
    for strategy in STRATEGIES:
        data=[r for r in rows if r['strategy']==strategy];stats=group(data)
        stats['language']={k:group([r for r in data if r['case']['language']==k]) for k in ('zh','en')}
        stats['literalEligible']=group([r for r in data if explicit_name_id(r['case']['text'],r['case']['skills'])])
        stats['nonliteral']=group([r for r in data if not explicit_name_id(r['case']['text'],r['case']['skills'])])
        pairs={c['caseId']:[r for r in data if r['case']['caseId']==c['caseId']] for c in protocol['cases']}
        stats['consistentCases']=sum(len(v)==2 and all(r['available'] for r in v) and
            len({(r['selection']['status'],r['selection']['skill_id']) for r in v})==1 for v in pairs.values())
        result[strategy]=stats
    return result


def freeze(out):
    out.mkdir(parents=True,exist_ok=False);cases=build_cases(catalog('R5CW134LLBZ'));trials=[];rng=random.Random(347882)
    for repeat in range(2):
        block=list(range(24));rng.shuffle(block)
        for index in block:
            order=list(STRATEGIES);rng.shuffle(order);trials.append(dict(index=index,repeat=repeat,order=order))
    hashes={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in SOURCES}
    write(out/'protocol.json',dict(cases=cases,trials=trials,sourceHashes=hashes,maxRemoteCalls=192,
        threshold=.90,timeoutSeconds=45,retries=0,selectionOnly=True,syntheticCatalogsNotExecutable=True))
    print('Frozen 24 instructions x 2 repeats x 4 strategies; no API yet.',flush=True)


def run(out):
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'))
    for name,h in protocol['sourceHashes'].items():
        assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()==h,'Frozen source changed'
    folder=out/'trials';folder.mkdir(exist_ok=False);os.environ['OPENAI_API_KEY']=read_key();rows=[];fatal=0
    for trial in protocol['trials']:
        case=protocol['cases'][trial['index']]
        for strategy in trial['order']:
            row=measure(strategy,case['text'],case['skills']);row.update(case=case,repeat=trial['repeat']);score(row)
            rows.append(row);write(folder/f'{len(rows):03d}-{strategy}.json',row);write(out/'results.json',rows)
            write(out/'summary.json',summarize(rows,protocol))
            print(json.dumps(dict(n=len(rows),strategy=strategy,case=case['caseId'],correct=row['correct'],
                ms=row['ms'],calls=row['remoteCalls'],error=row.get('error'))),flush=True)
            fatal=fatal+1 if row.get('error') in ('HTTP_401','HTTP_402','HTTP_403','HTTP_429') else 0
            if fatal>=3:
                write(out/'stopped.json',dict(reason='CONSECUTIVE_ACCOUNT_ERRORS',completed=len(rows)));return


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','run']);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    freeze(a.output) if a.mode=='freeze' else run(a.output)
