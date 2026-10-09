"""Held-out sentences for a narrow structural guard, not proof of general accuracy."""
import argparse
import copy
import hashlib
import json
import os
import random
import time
from pathlib import Path
from compiler import ModelError
from jev_reliability import build_cases,score,summarize,SOURCES
from jev_selection import select_jev,remote
from jev_selection_benchmark import call
from catalog_uniqueness import guard_selection
from win_credentials import read_key
from workflow_experiment import write


def cases(base):
    original=next(s['id'] for s in base if s['finalGoals']==[1,60,1,1])
    fan=next(s['id'] for s in base if s['finalGoals']==[None,None,1,1])
    duplicate=next(c['skills'] for c in build_cases(base) if c['variant']=='duplicate')
    copy_id=duplicate[-1]['id']
    fan_id=hashlib.sha256(b'guard-confirmation-fan-copy').hexdigest()
    fan_copy=copy.deepcopy(base)+[dict(id=fan_id,name='风扇低档备份 / FanLow Copy',
        goal='Turn on fan at low speed; keep lamp unchanged.',finalGoals=[None,None,1,1])]
    specs=[
        ('named_original',duplicate,original,'invoke','请执行我保存的阅读60技能。','Please execute my saved Reading60 skill.'),
        ('named_copy',duplicate,copy_id,'invoke','请启动阅读60备份流程。','Start the saved Reading60 Copy workflow.'),
        ('named_full',duplicate,original,'invoke','请你运行“阅读60 / Reading60”技能。','Activate "阅读60 / Reading60" skill.'),
        ('named_fan_copy',fan_copy,fan_id,'invoke','运行风扇低档备份。','Run the saved FanLow Copy skill.'),
        ('ambiguous_reading',duplicate,None,'clarify','阅读灯开启并调到六成亮，同时风扇开启调到低速。','Switch the reading lamp on at sixty percent brightness, with the fan switched on at low speed.'),
        ('ambiguous_fan',fan_copy,None,'clarify','灯保持原样，只把风扇打开并改为低档。','Preserve the lamp; only switch on the fan at low speed.'),
        ('unspecified_copy',duplicate+fan_copy[-1:],None,'clarify','运行那个备份模式。','Start the copy mode.'),
        ('negation',duplicate,None,'reject','不要执行阅读60备份。','Please do not execute Reading60 Copy.')]
    rows=[]
    for category,skills,expected,status,zh,en in specs:
        for language,text in [('zh',zh),('en',en)]:
            rows.append(dict(caseId=category+'-'+language,category=category,variant='duplicate',language=language,
                text=text,skills=skills,expected=expected,expectedStatus=status))
    return rows


def replay(source,out):
    out.mkdir(parents=True,exist_ok=False)
    protocol=json.loads((source/'protocol.json').read_text(encoding='utf-8'))
    original=json.loads((source/'confirmation/results.json').read_text(encoding='utf-8'))
    rows=[]
    for raw in original:
        if raw['backend']!='jev': continue
        row=copy.deepcopy(raw); started=time.perf_counter()
        if row['available']: row['selection']=guard_selection(row['case']['text'],row['case']['skills'],row['selection'])
        row.update(guardOverheadMs=round((time.perf_counter()-started)*1000,4),offlineReplay=True)
        score(row); rows.append(row)
    write(out/'results.json',rows);write(out/'summary.json',summarize(rows,protocol))
    print('Saved guard replay of 96 existing Jev responses; zero new API calls.',flush=True)


def freeze(out):
    out.mkdir(parents=True,exist_ok=False); root=Path(__file__).resolve().parents[1]
    base=json.loads((root/'evaluation/jev-skill-selection/protocol.json').read_text(encoding='utf-8'))['skills']
    dataset=cases(base);rng=random.Random(912771);trials=[]
    for repeat in range(2):
        order=list(range(len(dataset)));rng.shuffle(order)
        for index in order:
            services=['gpt','jev'];rng.shuffle(services);trials.append(dict(index=index,repeat=repeat,order=services))
    hashes={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in SOURCES+['catalog_uniqueness.py','jev_guard_confirmation.py']}
    write(out/'protocol.json',dict(cases=dataset,trials=trials,repeats=2,maxRequests=64,
        sourceHashes=hashes,threshold=.90,retries=0,developmentDiscoveredFailure='equivalent goals',syntheticCatalogsNotExecutable=True))
    print('Frozen 16 new sentences x 2 repeats x 2 services = 64 real requests.',flush=True)


def guarded_call(text,skills):
    started=time.perf_counter();responses=[]
    try:
        def capture(body):
            response=remote(body);responses.append(response);return response
        result=select_jev(text,skills,transport=capture)
        response=responses[-1]
        return dict(backend='jev',available=True,selection=result,ms=round((time.perf_counter()-started)*1000,2),
            metadata=dict(model=response['model'],usage=response.get('usage'),answer=response['answers']['selection']))
    except Exception as e:
        code=str(e) if isinstance(e,ModelError) else type(e).__name__
        return dict(backend='jev',available=False,error=code,ms=round((time.perf_counter()-started)*1000,2))


def run(out):
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'))
    for name,expected in protocol['sourceHashes'].items():
        assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()==expected,'Source changed after freeze'
    folder=out/'confirmation';folder.mkdir(exist_ok=False);os.environ['OPENAI_API_KEY']=read_key();rows=[];fatal={'gpt':0,'jev':0}
    for trial in protocol['trials']:
        case=protocol['cases'][trial['index']]
        for backend in trial['order']:
            row=guarded_call(case['text'],case['skills']) if backend=='jev' else call('gpt',case['text'],case['skills'])
            row.update(case=case,repeat=trial['repeat']);score(row);rows.append(row)
            write(folder/f'{len(rows):03d}-{backend}.json',row);write(folder/'results.json',rows);write(folder/'summary.json',summarize(rows,protocol))
            print(json.dumps(dict(n=len(rows),backend=backend,case=case['caseId'],correct=row['correct'],unsafe=row['unsafeSuggestion'],ms=row['ms'])),flush=True)
            fatal[backend]=fatal[backend]+1 if row.get('error') in ('HTTP_401','HTTP_402','HTTP_403','HTTP_429') else 0
            if fatal[backend]>=3:
                write(folder/'stopped.json',dict(completed=len(rows),backend=backend,error=row['error']));return
    print('Completed 64 real guarded/GPT calls; failures retained.',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('mode',choices=['replay','freeze','run'])
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--source',type=Path)
    args=parser.parse_args()
    if args.mode=='replay':replay(args.source,args.output)
    elif args.mode=='freeze':freeze(args.output)
    else:run(args.output)
