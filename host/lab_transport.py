"""Host-only lab controller. Never part of model tools or the user planning context."""
import hashlib,json,subprocess,time,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
ADB='D:/python_code/closed-loop-gui-agent/tools/android-sdk/platform-tools/adb.exe'
HOSTS={'R5CW134LLBZ','emulator-5556'}
def adb(host,*args,input=None,timeout=20):
    if host not in HOSTS:raise ValueError('UNKNOWN_HOST')
    r=subprocess.run([ADB,'-s',host,*args],input=input,capture_output=True,timeout=timeout)
    if r.returncode:raise RuntimeError('ADB_ERROR: '+r.stderr.decode(errors='replace')[:200])
    return r.stdout
def execute(host,plan,*,mode='TEST_FIXTURE',writes=None,confirmed=True,cancel_after=None):
    raw=json.dumps(plan,ensure_ascii=False,separators=(',',':')).encode()
    # shell program is fixed; JSON travels only through stdin, never shell interpolation.
    adb(host,'shell','run-as','edu.sydney.probe','sh','-c',"'cat > files/flow-incoming.json'",input=raw)
    rid=uuid.uuid4().hex;start=time.monotonic()
    params={'request_id':rid,'operation':'execute','mode':mode,'plan_raw_hash':hashlib.sha256(raw).hexdigest(),
            'allowed_writes':','.join(sorted(plan['actual_write_set'] if writes is None else writes))}
    args=['shell','am','broadcast','--receiver-foreground','-a','edu.sydney.probe.FLOW_AUDIT','-n','edu.sydney.probe/.FlowAuditReceiver','--ez','confirmed',str(confirmed).lower()]
    # adb shell joins argv into a shell command. An empty string must remain a token.
    for k,v in params.items():args+=['--es',k,v if v else "''"]
    pool=ThreadPoolExecutor(max_workers=1)
    dispatch=pool.submit(adb,host,*args)
    sent=False
    while time.monotonic()-start<13:
        if cancel_after is not None and not sent and time.monotonic()-start>=cancel_after:
            cancel(host);sent=True
        try:
            r=adb(host,'shell','run-as','edu.sydney.probe','cat','files/flow-audit-'+rid+'.json')
            result=json.loads(r);result['transport_host']=host;result['transport_latency_ms']=(time.monotonic()-start)*1000
            result['cancel_dispatched']=sent
            pool.shutdown(wait=False)
            return result
        except (RuntimeError,json.JSONDecodeError):pass
        if dispatch.done():dispatch.result()  # propagate a real transport error; never resend
        time.sleep(.08)
    pool.shutdown(wait=False)
    return {'request_id':rid,'final_status':'TRANSPORT_TIMEOUT','verification_result':False,'transport_host':host}
def cancel(host):
    return adb(host,'shell','am','broadcast','--receiver-foreground','-a','edu.sydney.probe.FLOW_AUDIT','-n','edu.sydney.probe/.FlowAuditReceiver','--es','request_id',uuid.uuid4().hex,'--es','operation','cancel')
