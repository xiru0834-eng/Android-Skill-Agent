"""Small fixed development set, not a held-out accuracy benchmark."""
import argparse
import json
import os
from pathlib import Path
import time
from intent import understand
from win_credentials import read_key

CASES=[
    ('zh_on','打开阅读灯和风扇','invoke',True,True),
    ('en_on','Turn on the reading lamp and the desk fan.','invoke',True,True),
    ('zh_off','请把灯和风扇都关掉','invoke',False,False),
    ('en_off','Please turn both the lamp and fan off.','invoke',False,False),
    ('zh_mix','打开阅读灯，关闭风扇','invoke',True,False),
    ('en_mix','Turn off the lamp and turn on the fan.','invoke',False,True),
    ('zh_single','只开灯，不要改变风扇','invoke',True,None),
    ('en_single','Switch the fan off and leave the lamp unchanged.','invoke',None,False),
    ('zh_ambiguous','把那个打开','clarify',None,None),
    ('en_ambiguous','Turn it on.','clarify',None,None),
    ('zh_unsupported','开灯并把空调调到24度','reject',None,None),
    ('en_unsupported','Turn on the lamp and set the AC to 24 degrees.','reject',None,None)]


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    os.environ['OPENAI_API_KEY']=read_key()
    (args.output/'protocol.json').write_text(json.dumps(dict(scope='development, 12 fixed utterances, one run each; no phone actions',cases=CASES),ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[]
    try:
        for name,text,status,lamp,fan in CASES:
            start=time.perf_counter()
            try:
                result=understand(text)
                row=dict(name=name,result=result,passed=(result['status'],result['lamp'],result['fan'])==(status,lamp,fan))
            except Exception as error:
                row=dict(name=name,error=type(error).__name__+': '+str(error),passed=False)
            row['elapsed_ms']=round((time.perf_counter()-start)*1000);rows.append(row)
            print(json.dumps(row,ensure_ascii=True),flush=True)
            if 'error' in row: break
    finally:
        (args.output/'results.json').write_text(json.dumps(dict(completed=len(rows),passed=sum(r['passed'] for r in rows),rows=rows),ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__': main()
