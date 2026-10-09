"""Frozen scope-sensitive bilingual selection test, never executes returned skills."""
import argparse,json,secrets,time,urllib.request,random
from pathlib import Path
from named_language_evaluation import catalog
from named_journey_device import prefs
from workflow_experiment import write
from skill_selection import validate_selection
from partial_journey import SKILLS

CASES=[
 ('执行只灯60','lamp'),('Run LampOnly60.','lamp'),
 ('打开灯并设置亮度60%，不要改风扇。','lamp'),('Turn on the lamp at 60 percent; leave the fan as it is.','lamp'),
 ('执行只风扇低档','fan'),('Run FanOnlyLow.','fan'),
 ('打开风扇设为低档，灯保持不变。','fan'),('Turn on the fan at low speed without changing the lamp.','fan'),
 ('开灯',None),('Turn on the fan.',None),('不要执行只灯60',None),('Cancel FanOnlyLow.',None),
 ('灯亮度改成55%',None),('Run LampOnly60 but use 80 percent.',None),
 ('只打开灯并设为60%，同时不要改灯的亮度',None),('Is FanOnlyLow already running?',None)]

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','run']);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='freeze':
        a.output.mkdir(parents=True,exist_ok=False);cases=[dict(text=t,expected=k) for t,k in CASES];random.Random(2401).shuffle(cases)
        write(a.output/'protocol.json',dict(cases=cases,selectionOnly=True));return
    protocol=json.loads((a.output/'protocol.json').read_text(encoding='utf-8'));skills=catalog('R5CW134LLBZ');write(a.output/'catalog.json',skills)
    ids={k:next(s['id'] for s in skills if s['finalGoals']==v['target']) for k,v in SKILLS.items()};token=prefs('R5CW134LLBZ','language_connection')['pairing'];rows=[]
    for i,case in enumerate(protocol['cases']):
        out=a.output/f'case-{i:03d}';out.mkdir(exist_ok=False);body=dict(request_id=secrets.token_hex(16),text=case['text'],skills=skills);write(out/'request.json',body);start=time.monotonic()
        try:
            req=urllib.request.Request('http://127.0.0.1:8765/v1/skill-selections',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=55) as r:result=json.load(r)
            assert result.pop('request_id')==body['request_id'];validate_selection(result,skills)
            correct=result['status']=='invoke' and result['skill_id']==ids[case['expected']] if case['expected'] else result['status']!='invoke' and result['skill_id'] is None
            row=dict(case=case,result=result,correct=correct,ms=round((time.monotonic()-start)*1000))
        except Exception as e:row=dict(case=case,correct=False,error=type(e).__name__,ms=round((time.monotonic()-start)*1000))
        rows.append(row);write(out/'result.json',row);write(a.output/'results.json',rows);print(json.dumps(dict(index=i,correct=row['correct'],ms=row['ms'])),flush=True)

if __name__=='__main__':main()
