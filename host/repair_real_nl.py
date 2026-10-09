"""Current authorization: fixed, disjoint session allocations; no automatic retries."""
import argparse, json, socket, subprocess, sys, time
from pathlib import Path
import g3_device_eval as g3
from lab_transport import adb
from prepare_g1 import save
ROOT=Path(__file__).parent

# Aggregate authorization 32 attempts / $1; each new session has a disjoint allocation.
# Main session has no right to spend fresh-session allocation.
ALLOCATIONS={'timing-emulator':(1,50_000_000,1,50_000_000),
             'final-phone':(7,300_000_000,1,50_000_000),
             'final-emulator':(7,300_000_000,1,50_000_000),
             'repeat-emulator-1':(1,50_000_000,1,50_000_000),
             'repeat-emulator-2':(1,50_000_000,1,50_000_000)}

def run(host,out,phase):
    if out.exists():raise ValueError('PRESERVE_OLD_BATCH')
    caps=ALLOCATIONS[phase];save(ROOT/'evidence/flow-deadline-repair/r1/real-nl'/('allocation-'+out.name+'.json'),
        {'human_authorized':True,'max_attempts':32,'max_estimated_usd':1,'automatic_retries':0,
         'allocations':ALLOCATIONS,'current_phase':phase,'current_output':str(out),'input_byte_cap':65536,'output_token_cap_actual':512,
         'failure_timeout_late_attempts_counted':True,'actual_invoice':'UNKNOWN'})
    # Count every previous session, including interrupted and UNKNOWN_RESERVED.
    ledgers=[json.loads(p.read_text(encoding='utf-8')) for p in (ROOT/'evidence/flow-deadline-repair/r1').rglob('paid-budget.json')]
    attempts=sum(x['attempts'] for x in ledgers);exposure=sum(x['exposureNanoUsd'] for x in ledgers)
    if attempts+caps[0]+caps[2]>32 or exposure+caps[1]+caps[3]>1_000_000_000:raise ValueError('GLOBAL_AUTHORIZATION_LIMIT')
    saved_reconnect=g3.reconnect
    def current_reconnect(h):return saved_reconnect(h,ROOT/'private/flow-deadline-repair-r1'/h/'snapshot.json')
    def bounded_bridge(h,knowledge,path,port,max_calls):
        fresh=path.name=='fresh-session';n,money=caps[2:] if fresh else caps[:2]
        if n<1:raise ValueError('UNAUTHORIZED_SESSION')
        log=(path/'bridge.log').open('w',encoding='utf-8')
        proc=subprocess.Popen([sys.executable,'-u',str(ROOT/'flow_bridge.py'),str(knowledge),str(path/'model-audit'),
            '--host',h,'--port',str(port),'--max-calls',str(n),'--max-nano-usd',str(money)],cwd=ROOT,
            stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        try:
            for _ in range(80):
                if proc.poll() is not None:raise ValueError('BRIDGE_START_FAILED')
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.1):break
                except OSError:time.sleep(.05)
            else:raise ValueError('BRIDGE_NOT_READY')
            adb(h,'reverse','tcp:8765','tcp:'+str(port))
            save(path/'gateway-session.json',{'pid':proc.pid,'started_monotonic_ns':time.monotonic_ns(),'fresh_process':fresh,
                'max_calls':n,'max_nano_usd':money,'automatic_retry':False})
            return proc,log
        except Exception:proc.terminate();proc.wait(5);log.close();raise
    g3.reconnect=current_reconnect;g3.bridge=bounded_bridge
    knowledge=ROOT/('evidence/g2-native-reviewed-knowledge-r2.json' if host=='R5CW134LLBZ' else 'evidence/g4-real-package-transfer-r1/target-native-knowledge.json')
    only=None if phase.startswith('final-') else ['explicit','new_session']
    g3.run(host,knowledge,out,49721 if host=='R5CW134LLBZ' else 49722,case_names=only)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--phase',choices=ALLOCATIONS,required=True);a=p.parse_args();run(a.host,a.out,a.phase)
