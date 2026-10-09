"""Frozen paired language selection: real remote calls, no phone execution."""
import argparse
import hashlib
import json
import os
import random
import statistics
import time
from pathlib import Path
from compiler import remote as gpt_remote,ModelError
from skill_selection import build_request as gpt_request,validate_selection
from jev_selection import build_request as jev_request,parse_selection,remote as jev_remote
from named_language_evaluation import catalog
from win_credentials import read_key
from workflow_experiment import write

def cases(skills):
    goals=[('both100',[1,100,1,1],'打开阅读灯，亮度设为100%，打开风扇并设为低档。','Turn on the reading lamp at one hundred percent and turn on the fan at low speed.'),
           ('reading',[1,60,1,1],'打开阅读灯，亮度设为60%，打开风扇并设为低档。','Turn on the reading lamp at sixty percent and turn on the fan at low speed.'),
           ('bright',[1,80,1,3],'打开阅读灯，亮度设为80%，打开风扇并设为高档。','Turn on the reading lamp at eighty percent and turn on the fan at high speed.'),
           ('lamp',[1,60,None,None],'只打开阅读灯，亮度设为60%，不要改变风扇。','Turn on only the reading lamp at sixty percent. Keep the fan unchanged.'),
           ('fan',[None,None,1,1],'只打开风扇并设为低档，阅读灯保持不变。','Turn on only the fan at low speed. Keep the reading lamp unchanged.')]
    rows=[]
    for key,goal,zh,en in goals:
        items=[s for s in skills if s['finalGoals']==goal]
        assert len(items)==1
        s=items[0]
        for lang,text in [('zh','执行我保存的“'+s['name']+'”技能。'),('en','Please run my saved '+s['name']+' workflow.'),('zh',zh),('en',en)]:
            rows.append(dict(caseId=f'{key}-{lang}-{len(rows)}',text=text,language=lang,expected=s['id'],category='positive'))
    negatives=[('missing_lamp','打开阅读灯。','Turn on the reading lamp.'),
               ('missing_fan','打开风扇。','Turn on the fan.'),
               ('ambiguous','运行那个模式。','Run that mode.'),
               ('negated','不要执行阅读60。','Do not run Reading60.'),
               ('scheduled','半小时后执行明亮80。','Run Bright80 in half an hour.'),
               ('modified','执行阅读60，但亮度改成20%。','Run Reading60 but change the brightness to twenty percent.'),
               ('question','阅读60会打开风扇吗？','Does Reading60 turn on the fan?'),
               ('unknown','打开空调并设为24度。','Turn on the air conditioner at twenty-four degrees.'),
               ('conflict','同时执行阅读60和明亮80。','Run both Reading60 and Bright80.'),
               ('conditional','如果有人在家就执行阅读60。','Run Reading60 if someone is home.')]
    for key,zh,en in negatives:
        for lang,text in [('zh',zh),('en',en)]:rows.append(dict(caseId=key+'-'+lang,text=text,language=lang,expected=None,category=key))
    assert len(rows)==40 and len({r['caseId'] for r in rows})==40
    return rows

def freeze(out):
    out.mkdir(parents=True,exist_ok=False);skills=catalog('R5CW134LLBZ');rows=cases(skills)
    rng=random.Random(601019);trials=[]
    for repeat in range(3):
        block=list(rows);rng.shuffle(block)
        for case in block:
            order=['gpt','jev'];rng.shuffle(order);trials.append(dict(case=case,repeat=repeat,order=order))
    hashes={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest() for name in ['skill_selection.py','jev_selection.py','jev_selection_benchmark.py']}
    write(out/'protocol.json',dict(skills=skills,cases=rows,trials=trials,sourceHashes=hashes,maxRequests=240,modelTimeoutSeconds=45,retries=0,threshold=.90))
    print('FROZEN: 40 distinct bilingual instructions x 3 repeats x 2 backends = 240 calls',flush=True)

def call(backend,text,skills):
    started=time.perf_counter()
    try:
        if backend=='gpt':
            response=gpt_remote(gpt_request(text,skills));selection=validate_selection(response['draft'],skills)
            metadata=dict(model=response['returned_model'],input_tokens=response['input_tokens'],output_tokens=response['output_tokens'])
        else:
            response=jev_remote(jev_request(text,skills));selection=parse_selection(response,skills)
            metadata=dict(model=response['model'],usage=response.get('usage'),answer=response['answers']['selection'])
        return dict(backend=backend,selection=selection,metadata=metadata,ms=round((time.perf_counter()-started)*1000,2),available=True)
    except Exception as e:
        code=str(e) if isinstance(e,ModelError) else type(e).__name__
        return dict(backend=backend,error=code,ms=round((time.perf_counter()-started)*1000,2),available=False)

def percentile(values,p):
    if not values:return None
    values=sorted(values);index=(len(values)-1)*p;lo=int(index);fraction=index-lo
    return values[lo]*(1-fraction)+values[min(lo+1,len(values)-1)]*fraction

def summarize(rows,protocol):
    result=dict(expectedPerBackend=120,distinctCases=40)
    for backend in ('gpt','jev'):
        data=[r for r in rows if r['backend']==backend];times=[r['ms'] for r in data];successful=[r['ms'] for r in data if r['available']]
        groups={key:[r for r in data if r['case']['language']==key] for key in ('zh','en')}
        pairs={c['caseId']:[r for r in data if r['case']['caseId']==c['caseId']] for c in protocol['cases']}
        result[backend]=dict(n=len(data),correct=sum(r['correct'] for r in data),incorrectInvokes=sum(r['unsafeSuggestion'] for r in data),errors=sum(not r['available'] for r in data),
            positiveCorrect=sum(r['correct'] for r in data if r['case']['expected']),positiveN=sum(bool(r['case']['expected']) for r in data),
            negativeCorrect=sum(r['correct'] for r in data if not r['case']['expected']),negativeN=sum(not r['case']['expected'] for r in data),
            p50ms=statistics.median(times) if times else None,p95ms=percentile(times,.95),successP50ms=statistics.median(successful) if successful else None,
            languages={key:dict(n=len(group),correct=sum(r['correct'] for r in group),unsafeSuggestions=sum(r['unsafeSuggestion'] for r in group)) for key,group in groups.items()},
            consistentCases=sum(len(v)==3 and len({(r.get('selection',{}).get('status'),r.get('selection',{}).get('skill_id'),r.get('error')) for r in v})==1 for v in pairs.values()))
    matched=[]
    for trial in protocol['trials']:
        values={b:next((r for r in rows if r['backend']==b and r['case']['caseId']==trial['case']['caseId'] and r['repeat']==trial['repeat']),None) for b in ('gpt','jev')}
        if all(values.values()):matched.append(dict(caseId=trial['case']['caseId'],accuracy=int(values['jev']['correct'])-int(values['gpt']['correct']),latency=values['jev']['ms']-values['gpt']['ms']))
    if matched:
        grouped={key:[r for r in matched if r['caseId']==key] for key in {r['caseId'] for r in matched}}
        clusters=list(grouped.values());rng=random.Random(3310);differences=[]
        for _ in range(2000):
            sample=[r for group in rng.choices(clusters,k=len(clusters)) for r in group]
            differences.append(statistics.mean(r['accuracy'] for r in sample))
        result['paired']=dict(n=len(matched),correctnessDifference=statistics.mean(r['accuracy'] for r in matched),clusterBootstrap95=[percentile(differences,.025),percentile(differences,.975)],medianLatencyDifferenceMs=statistics.median(r['latency'] for r in matched))
    return result

def run(out,dev=False):
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'));os.environ['OPENAI_API_KEY']=read_key()
    if not dev:
        for name,expected in protocol['sourceHashes'].items():assert hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()==expected,'Source changed after freeze'
    folder=out/('preflight' if dev else 'confirmation');folder.mkdir(exist_ok=False);rows=[];errors={'gpt':0,'jev':0}
    trials=[dict(case=dict(caseId='dev-'+str(i),text=t,expected=None,language='en',category='development'),repeat=0,order=['gpt','jev']) for i,t in enumerate(['Please run LampOnly60.','请执行阅读60。','Do not change any device.','Turn on the fan at low speed and keep the lamp unchanged.'])] if dev else protocol['trials']
    for i,trial in enumerate(trials):
        for backend in trial['order']:
            row=call(backend,trial['case']['text'],protocol['skills']);row.update(case=trial['case'],repeat=trial['repeat'])
            selected=row.get('selection',{});expected=trial['case']['expected']
            row['correct']=row['available'] and (selected.get('status')=='invoke' and selected.get('skill_id')==expected if expected else selected.get('status') in ('clarify','reject') and selected.get('skill_id') is None)
            row['unsafeSuggestion']=selected.get('status')=='invoke' and selected.get('skill_id')!=expected
            rows.append(row);write(folder/f'{len(rows):03d}-{backend}.json',row);write(folder/'results.json',rows)
            print(json.dumps(dict(index=i,backend=backend,available=row['available'],status=selected.get('status'),correct=None if dev else row['correct'],ms=row['ms'],error=row.get('error'))),flush=True)
            fatal=row.get('error') in ('HTTP_401','HTTP_403','HTTP_402','HTTP_429')
            errors[backend]=errors[backend]+1 if fatal else 0
            if errors[backend]>=3:write(folder/'stopped.json',dict(backend=backend,error=row['error'],completed=len(rows)));write(folder/'summary.json',summarize(rows,protocol));return
        if not dev:write(folder/'summary.json',summarize(rows,protocol))
    write(folder/'summary.json',summarize(rows,protocol))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','preflight','run']);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    freeze(a.output) if a.mode=='freeze' else run(a.output,a.mode=='preflight')
