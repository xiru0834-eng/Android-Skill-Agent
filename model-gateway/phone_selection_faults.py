"""Phone stale-response safeguards with explicitly INJECTED, not model responses."""
import argparse
import json
import re
import threading
import time
from pathlib import Path
from compiler import ModelError
from intent_bridge import BridgeServer
from named_journey_device import prefs,home,library,tap,text,snap,PROBE,APP
from transfer_run import private
from workflow_capture import tree
from workflow_experiment import adb,write


def main(out):
    out.mkdir(parents=True,exist_ok=False); serial='R5CW134LLBZ'
    before=prefs(serial); oracle=private(serial,APP,'workflow-oracle.json')
    token=prefs(serial,'language_connection')['pairing']
    prior=next((line.split()[-1] for line in adb(serial,'reverse','--list').splitlines()
        if len(line.split())>=3 and line.split()[-2]=='tcp:8765'),None)
    if prior and not re.fullmatch(r'tcp:\d+',prior): raise ValueError('INVALID_REVERSE')
    library(serial)
    saved_input=next(n.get('text','') for n in tree(serial).iter('node') if n.get('resource-id')==PROBE+':id/libraryInput')
    mode=['cancel']; entered=threading.Event(); release=threading.Event(); finished=threading.Event(); calls=[]
    def selector(command,skills):
        calls.append(dict(text=command,mode=mode[0],injected=True)); write(out/'injected-calls.json',calls)
        entered.set()
        if not release.wait(30): raise ModelError('TEST_WAIT_EXPIRED')
        try:
            if mode[0]=='error': raise ModelError('NETWORK_OR_TIMEOUT')
            if mode[0]=='reject': return dict(status='reject',skill_id=None,message='Controlled injected rejection; nothing ran.')
            return dict(status='invoke',skill_id=skills[0]['id'],message='Controlled stale proposal; nothing ran.')
        finally: finished.set()
    server=BridgeServer(('127.0.0.1',0),token,max_calls=12,skill_selector=selector)
    worker=threading.Thread(target=server.serve_forever,daemon=True); worker.start()
    rows=[]
    write(out/'protocol.json',dict(injectedResponses=True,remoteModelCalls=0,repeats=2,
        scenarios=['cancel','edit','leave','error','reject'],requiresNoExecution=True))
    try:
        adb(serial,'reverse','tcp:8765','tcp:'+str(server.server_port))
        for repeat in range(2):
            for scenario in ['cancel','edit','leave','error','reject']:
                mode[0]=scenario; entered.clear(); release.clear(); finished.clear()
                library(serial); text(serial,'libraryInput','Run Transfer Bench.'); tap(serial,'libraryChoose')
                assert entered.wait(5), 'Selection request not received'
                if scenario=='cancel': tap(serial,'libraryCancel')
                elif scenario=='edit': text(serial,'libraryInput','Do not run any skill.')
                elif scenario=='leave': home(serial)
                release.set(); assert finished.wait(5); time.sleep(1)
                ui=tree(serial)
                assert not any(n.get('resource-id')=='android:id/button1' for n in ui.iter('node')), 'Unexpected confirmation'
                now=prefs(serial)
                assert now['library']==before['library'] and now.get('approved')==before.get('approved')
                assert now.get('result')==before.get('result') and private(serial,APP,'workflow-oracle.json')==oracle
                if scenario=='error':
                    status=next(n.get('text','') for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/libraryStatus')
                    assert 'NETWORK_OR_TIMEOUT' not in status and ('未' in status or '失败' in status or 'not' in status or 'failed' in status.lower())
                snap(serial,out/f'{repeat}-{scenario}.png')
                rows.append(dict(scenario=scenario,repeat=repeat,status='PASS',noConfirmation=True,
                    noExecution=True,catalogueUnchanged=True,oracleExactUnchanged=True,injected=True))
                write(out/'results.json',rows); print('PASS injected phone '+scenario+' repeat '+str(repeat),flush=True)
    except Exception as e:
        write(out/'failure.json',dict(error=type(e).__name__,reason=str(e))); raise
    finally:
        release.set(); server.shutdown(); server.server_close(); worker.join(timeout=3)
        if prior: adb(serial,'reverse','tcp:8765',prior)
        else: adb(serial,'reverse','--remove','tcp:8765')
        library(serial); text(serial,'libraryInput',saved_input if saved_input else ' '); home(serial)
        write(out/'restored.json',dict(reverseRestored=True,inputRestored=True,catalogueUnchanged=prefs(serial)['library']==before['library'],
            approvalUnchanged=prefs(serial).get('approved')==before.get('approved'),oracleUnchanged=private(serial,APP,'workflow-oracle.json')==oracle))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--output',type=Path,required=True); a=p.parse_args(); main(a.output)
