"""Fresh literal-miss confirmation; not a rerun of failures from the first set."""
import argparse
import hashlib
import json
import os
import random
from pathlib import Path
import model_coordination as bench
from selection_routing import select_routed
from named_language_evaluation import catalog
from workflow_experiment import write
from win_credentials import read_key
from functools import partial

FULL_SELECTOR=partial(select_routed,compact=False)


def freeze(out):
    out.mkdir(parents=True,exist_ok=False);skills=catalog('R5CW134LLBZ')
    ids={tuple(s['finalGoals']):s['id'] for s in skills}
    specs=[
        ('polite-reading',ids[(1,60,1,1)],'我想用阅读60这个保存好的流程，现在开始。','Go ahead with my saved Reading60 workflow now.'),
        ('named-lamp',ids[(1,60,None,None)],'我要使用名为只灯60的技能，按保存的设置执行。','Use the workflow called LampOnly60, with its saved settings.'),
        ('named-fan',ids[(None,None,1,1)],'接下来就按只风扇低档这个技能执行吧。','Let us use the saved FanOnlyLow skill now.'),
        ('named-bright',ids[(1,80,1,3)],'现在就用明亮80，所有参数按保存好的来。','Bright80 is the saved workflow I want you to execute now.'),
        ('explain-only',None,'请说明只灯60的用途，不执行它。','Describe what LampOnly60 does; do not execute it.'),
        ('condition',None,'如果温度超过25度再运行阅读60，现在不要执行。','Only execute Reading60 if the temperature is above twenty-five degrees; not now.')]
    cases=[]
    for category,expected,zh,en in specs:
        for lang,text in [('zh',zh),('en',en)]:
            assert bench.explicit_name_id(text,skills) is None
            cases.append(dict(caseId=category+'-'+lang,category=category,language=lang,text=text,skills=skills,expected=expected))
    rng=random.Random(462297);trials=[]
    for repeat in range(2):
        block=list(range(12));rng.shuffle(block)
        for index in block:
            order=['G','F','R'];rng.shuffle(order);trials.append(dict(index=index,repeat=repeat,order=order))
    sources=bench.SOURCES+['coordination_holdout.py']
    write(out/'protocol.json',dict(cases=cases,trials=trials,maxCalls=72,retries=0,repeats=2,threshold=.90,
        sourceHashes={n:hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest() for n in sources},
        onlyLiteralMisses=True,selectionOnly=True))
    print('Frozen 12 fresh literal-miss instructions x 2 repeats x 3 strategies',flush=True)


def run(out):
    p=json.loads((out/'protocol.json').read_text(encoding='utf-8'))
    for n,h in p['sourceHashes'].items():assert hashlib.sha256(Path(__file__).with_name(n).read_bytes()).hexdigest()==h
    (out/'trials').mkdir(exist_ok=False);os.environ['OPENAI_API_KEY']=read_key();rows=[];fatal=0
    for trial in p['trials']:
        for strategy in trial['order']:
            c=p['cases'][trial['index']];r=bench.measure(strategy,c['text'],c['skills'],selector=FULL_SELECTOR if strategy=='F' else None);r.update(case=c,repeat=trial['repeat']);bench.score(r)
            rows.append(r);write(out/'trials'/f'{len(rows):03d}-{strategy}.json',r);write(out/'results.json',rows)
            write(out/'summary.json',{k:bench.group([r for r in rows if r['strategy']==k]) for k in ['G','F','R']})
            print(json.dumps(dict(n=len(rows),strategy=strategy,case=c['caseId'],correct=r['correct'],ms=r['ms'],error=r.get('error'))),flush=True)
            fatal=fatal+1 if r.get('error') in ('HTTP_401','HTTP_402','HTTP_403','HTTP_429') else 0
            if fatal>=3:write(out/'stopped.json',dict(reason='CONSECUTIVE_ACCOUNT_ERRORS',completed=len(rows)));return


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','run']);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    freeze(a.output) if a.mode=='freeze' else run(a.output)
