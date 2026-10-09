"""One bounded audited bridge session. Secrets stay in memory, never in evidence."""
import argparse
import os
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from compiler import remote
from intent_bridge import BridgeServer
from workflow_compile import compile_trace
from skill_selection import select_skill
from win_credentials import read_key
from workflow_experiment import adb,write

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--max-calls',type=int,default=60);a=p.parse_args()
    if not 1<=a.max_calls<=60:p.error('max-calls must be 1..60')
    a.output.mkdir(parents=True,exist_ok=False)
    os.environ['OPENAI_API_KEY']=read_key()
    prefs=ET.fromstring(adb('R5CW134LLBZ','shell','run-as','edu.sydney.probe','cat','shared_prefs/language_connection.xml'))
    token=next((n.text for n in prefs if n.get('name')=='pairing'),'')
    if not re.fullmatch('[a-f0-9]{48}',token):raise RuntimeError('Existing pairing unavailable')
    count=0
    def transport(body):
        nonlocal count
        index=count;count+=1;out=a.output/f'call-{index:03d}';out.mkdir()
        write(out/'request.json',body);started=time.monotonic()
        try:
            result=remote(body);write(out/'response.json',result);write(out/'timing.json',dict(ms=round((time.monotonic()-started)*1000),success=True))
            print('Remote call '+str(index)+' completed',flush=True);return result
        except Exception as e:
            write(out/'failure.json',dict(error=type(e).__name__,reason=str(e),ms=round((time.monotonic()-started)*1000)));raise
    server=BridgeServer(('127.0.0.1',8765),token,max_calls=a.max_calls,
        workflow_compiler=lambda tr:compile_trace(tr,transport),skill_selector=lambda text,skills:select_skill(text,skills,transport))
    adb('R5CW134LLBZ','reverse','tcp:8765','tcp:8765')
    print('Named workflow bridge ready; capped at '+str(a.max_calls)+' remote calls; USB loopback only.',flush=True)
    try:server.serve_forever()
    finally:server.server_close()

if __name__=='__main__':main()
