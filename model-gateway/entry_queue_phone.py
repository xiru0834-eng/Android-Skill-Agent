"""Zero-fee real-phone backlog test with injected immediate selection response."""
import argparse
import threading
import time
from pathlib import Path
from intent_bridge import BridgeServer
from named_journey_device import prefs,APP,home
from transfer_run import private
from workflow_experiment import adb,write

def run(out,repeats):
    out.mkdir(parents=True,exist_ok=False);serial='R5CW134LLBZ'
    before=prefs(serial);oracle=private(serial,APP,'workflow-oracle.json');token=prefs(serial,'language_connection')['pairing']
    old=next((v.split()[-1] for v in adb(serial,'reverse','--list').splitlines() if len(v.split())>=3 and v.split()[-2]=='tcp:8765'),None)
    calls=[]
    def choose(text,skills):
        calls.append(text)
        selected=next(s for s in skills if s['finalGoals']==[1,60,1,1])
        return dict(status='invoke',skill_id=selected['id'],message='Injected valid proposal for queue test only.')
    server=BridgeServer(('127.0.0.1',0),token,max_calls=4,skill_selector=choose)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start();rows=[]
    try:
        adb(serial,'reverse','tcp:8765','tcp:'+str(server.server_port))
        for repeat in range(repeats):
            started=time.monotonic()
            result=adb(serial,'shell','am','instrument','-w','edu.sydney.entrycontract/.EntryQueue',timeout=30)
            after=prefs(serial)
            protected=after==before and private(serial,APP,'workflow-oracle.json')==oracle
            row=dict(repeat=repeat,passed='PASS queued reply rejected' in result,protected=protected,
                instrumentation=result,wallMs=round((time.monotonic()-started)*1000),injected=True,modelCalls=0)
            rows.append(row);write(out/'results.json',rows)
            print('QUEUE '+('PASS' if row['passed'] else 'FAIL')+'; protected='+str(protected),flush=True)
            if not protected:raise RuntimeError('PROTECTED_STATE_CHANGED')
    finally:
        server.shutdown();server.server_close();worker.join(3)
        if old:adb(serial,'reverse','tcp:8765',old)
        else:adb(serial,'reverse','--remove','tcp:8765')
        home(serial)
        write(out/'restored.json',dict(reverseRestored=True,workflowPrefsUnchanged=prefs(serial)==before,
            targetUnchanged=private(serial,APP,'workflow-oracle.json')==oracle,calls=len(calls),modelCalls=0))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--repeats',type=int,default=2);a=p.parse_args();run(a.output,a.repeats)
