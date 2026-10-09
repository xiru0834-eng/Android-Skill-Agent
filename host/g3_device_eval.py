"""Real normal Android UI -> real GPT -> original Runtime, scored outside the Agent."""
import argparse,base64,copy,json,os,socket,subprocess,sys,time,uuid,threading
from pathlib import Path
from lab_transport import adb,ADB
from g1_device_eval import prepare,oracle
from install_candidate import health,SERVICE
from prepare_g1 import save
from product_ui_driver import drive as persistent_drive
ROOT=Path(__file__).parent

def reconnect(host,original_snapshot=None):
    # Diagnostic preparation only, preserves unrelated Accessibility services.
    current=adb(host,'shell','settings','get','secure','enabled_accessibility_services').decode().strip()
    # This evaluator owns the preceding instrumentation/force-stop operation;
    # Samsung removes the stopped service from this setting. Restore ONLY the
    # Probe entry that was enabled in the explicit pre-test snapshot.
    original=json.loads((Path(original_snapshot) if original_snapshot else ROOT/'private/before-v93'/host/'settings.json').read_text(encoding='utf-8'))
    original=original.get('settings',original)
    if 'secure.enabled_accessibility_services' in original:original={'enabled_accessibility_services':original['secure.enabled_accessibility_services']}
    if SERVICE not in current.split(':'):
        if SERVICE not in original['enabled_accessibility_services'].split(':'):raise ValueError('NO_PRIOR_SERVICE_PERMISSION')
        current=':'.join(x for x in current.split(':') if x!='null')
        current=(current+':' if current else '')+SERVICE
    others=':'.join(x for x in current.split(':') if x not in {SERVICE,'null'})
    # Clear the package stopped state before re-enabling the already-authorized
    # service. Wait for the actual owned binding to disappear; emulator dumpsys
    # uses a label, not the phone's component-id representation.
    adb(host,'shell','am','start','-f','0x14000000','-n','edu.sydney.probe/.MainActivity')
    adb(host,'shell','settings','put','secure','enabled_accessibility_services',others or 'null')
    until=time.monotonic()+8
    unbound=False
    while time.monotonic()<until:
        bound=adb(host,'shell','dumpsys','accessibility').decode().split('Bound services:',1)[-1].split('Enabled services:',1)[0]
        if 'edu.sydney.probe/' not in bound and 'label=Demo Probe' not in bound:unbound=True;break
        time.sleep(.1)
    if not unbound:raise ValueError('REAL_SERVICE_NOT_UNBOUND')
    adb(host,'shell','settings','put','secure','enabled_accessibility_services',current)
    adb(host,'shell','am','start','-n','edu.sydney.probe/.MainActivity')
    until=time.monotonic()+15
    ready=0
    while time.monotonic()<until:
        ready=ready+1 if health(host).get('final_status')=='READY' else 0
        if ready>=2:return
        time.sleep(.1)
    raise ValueError('REAL_SERVICE_NOT_CONNECTED')

def bridge(host,knowledge,out,port,max_calls):
    log=(out/'bridge.log').open('w',encoding='utf-8')
    proc=subprocess.Popen([sys.executable,'-u',str(ROOT/'flow_bridge.py'),str(knowledge),str(out/'model-audit'),
        '--host',host,'--port',str(port),'--max-calls',str(max_calls)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    for _ in range(80):
        if proc.poll() is not None:raise ValueError('BRIDGE_START_FAILED')
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=.1):break
        except OSError:time.sleep(.05)
    else:proc.terminate();raise ValueError('BRIDGE_NOT_READY')
    adb(host,'reverse','tcp:8765','tcp:'+str(port))
    return proc,log

def drive(host,text,*,review=False,cancel=False):
    proc=subprocess.Popen([ADB,'-s',host,'shell','am','instrument','-w','-e','text64',base64.b64encode(text.encode()).decode(),
        '-e','review',str(review).lower(),'-e','cancel',str(cancel).lower(),'edu.sydney.probe/.PublishedFlowUiChecks'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    lines=[];phase=threading.Event()
    def read():
        for raw in iter(proc.stdout.readline,b''):
            line=raw.decode('utf-8',errors='replace');lines.append(line)
            if 'phase=WAIT_REAL_SERVICE' in line:phase.set()
    reader=threading.Thread(target=read,daemon=True);reader.start()
    if not phase.wait(10):proc.terminate();raise ValueError('INSTRUMENTATION_PHASE_MISSING')
    reconnect(host)
    proc.wait(60);reader.join(2);raw=''.join(lines)
    parsed={}
    for line in raw.splitlines():
        if line.startswith('INSTRUMENTATION_RESULT: '):
            key,_,v=line[len('INSTRUMENTATION_RESULT: '):].partition('=');parsed[key]=v
    if 'selection' in parsed:parsed['selection']=json.loads(parsed['selection'])
    if 'result' in parsed:parsed['result']=json.loads(parsed['result'])
    return {'raw_instrumentation':raw,**parsed}

def run(host,knowledge,out,port,target_only=False,case_names=None):
    out.mkdir(parents=True,exist_ok=False)
    save(out/'original-reverse.json',{'list':adb(host,'reverse','--list').decode()})
    capsule=Path(knowledge).read_bytes()
    adb(host,'shell','run-as','edu.sydney.probe','sh','-c',"'cat > files/published-flow-incoming.json'",input=capsule)
    cases=[('explicit','Set bedroom light brightness to 20 percent.',50,20,'normal','SUCCESS',False),
           ('paraphrase','请把卧室灯的亮度调至80%，不要改变开关。',20,80,'normal','SUCCESS',False),
           ('missing','把卧室的灯调亮一点。',50,None,'normal','CLARIFY',False),
           ('illegal','Set bedroom light brightness to 101 percent.',50,None,'normal','REJECTED',False),
           ('already','将卧室灯亮度设置为60%。',60,60,'normal','NO_ACTION_REQUIRED',False),
           ('no_effect','Please set bedroom light brightness to60 percent.',50,60,'stubborn','NON_SUCCESS',False),
           ('cancel','Set bedroom light brightness to30 percent.',50,None,'normal','CANCELLED',True),
           ('new_session','Change the bedroom lamp brightness to60%, leave power alone.',100,60,'normal','SUCCESS',False)]
    if target_only:cases=[cases[0],cases[1],cases[2],cases[3],cases[7]]
    if case_names is not None:
        if not set(case_names)<=set(x[0] for x in cases):raise ValueError('UNKNOWN_REGISTERED_CASE')
        cases=[x for x in cases if x[0] in case_names]
    save(out/'registered-cases.json',[dict(name=n,text=t,initial=i,target=v,fault=f,expected=e,cancel=c) for n,t,i,v,f,e,c in cases])
    rows=[];proc=None;log=None;batch_error=None;active_case=None;started_at=None
    try:
        proc,log=bridge(host,knowledge,out,port,len(cases)+1)
        for index,(name,text,initial,wanted,fault,expected,cancel) in enumerate(cases):
            active_case=name;started_at=None
            if name=='new_session':
                proc.terminate();proc.wait(5);log.close();session=out/'fresh-session';session.mkdir()
                adb(host,'shell','am','force-stop','edu.sydney.probe')
                proc,log=bridge(host,knowledge,session,port,2)
            reconnect(host)
            before=prepare(host,uuid.uuid4().hex,(0,initial,0,22),fault)
            started=time.monotonic();started_at=started;used=persistent_drive(host,text,review=index==0,cancel=cancel)
            after=oracle(host);events=[{'property':e['property'],'value':e['value']} for e in after['events']]
            selection=used.get('selection',{});result=used.get('result',{})
            status=result.get('final_status') or {'clarify':'CLARIFY','reject':'REJECTED'}.get(selection.get('status')) or used.get('cancel_status')
            truth=copy.deepcopy(before['state'])
            permitted=[]
            if expected in {'SUCCESS','NO_ACTION_REQUIRED'}:
                truth['bedroom_light.brightnessPercent']=wanted
                if initial!=wanted:permitted=[{'property':'bedroom_light.brightnessPercent','value':wanted}]
            elif fault=='stubborn':permitted=[{'property':'bedroom_light.brightnessPercent','value':wanted}]
            # Missing an expected input is a failed task, not a wrong input.
            wrong=any(e not in permitted for e in events) or any(after['state'][k]!=truth[k] for k in truth if k!='bedroom_light.brightnessPercent')
            reported_success=status in {'SUCCESS','NO_ACTION_REQUIRED'}
            false_success=reported_success and (after['state']!=truth or events!=permitted or result.get('verification_result') is not True)
            expected_status=(status in {'FAILED','UNCONFIRMED','BUDGET_EXCEEDED'} if expected=='NON_SUCCESS' else
                             status=='USER_CANCELLED' if cancel else status==expected)
            real_entry=not reported_success or (result.get('mode')=='PUBLISHED_USER_TASK' and result.get('service_entry_hit') is True)
            passed=not used.get('error') and expected_status and after['state']==truth and not wrong and not false_success and real_entry
            row={'case':name,'host':host,'expected':expected,'before':before,'after':after,'ui':used,'final_status':status,
                'latency_ms':(time.monotonic()-started)*1000,'assessment':{'passed':bool(passed),'wrong_action':wrong,'false_success':false_success,'event_order':events},
                'channel':'REAL_GPT_NORMAL_UI_PUBLISHED_FLOW','flow_hash':json.loads(capsule)['flow_hash']}
            save(out/(name+'.json'),row);rows.append(row);print(name,status,passed,flush=True)
            if wrong or false_success:break
    except Exception as error:
        batch_error={'case':active_case,'error_type':type(error).__name__,'error':str(error),'completed_rows':len(rows),
            'phase':'UI_TEST_OR_PRODUCT_INTERRUPTED' if started_at is not None else 'INITIALIZATION_FAILED'}
        try:batch_error['final_oracle']=oracle(host)
        except Exception as read_error:batch_error['oracle_error']=type(read_error).__name__
        save(out/'interruption.json',batch_error)
        print('BATCH_INTERRUPTED',active_case,type(error).__name__,str(error),flush=True)
    finally:
        save(out/'summary.json',{'expected_behavior_passed':sum(r['assessment']['passed'] for r in rows),'executed':len(rows),'planned':len(cases),
            'real_language_positive_success':sum(r['assessment']['passed'] and r['expected'] in {'SUCCESS','NO_ACTION_REQUIRED'} for r in rows),
            'positive_total':sum(r['expected'] in {'SUCCESS','NO_ACTION_REQUIRED'} for r in rows),'wrong_action':sum(r['assessment']['wrong_action'] for r in rows),
            'false_success':sum(r['assessment']['false_success'] for r in rows),'source':'G2_ACTUAL_PUBLISHED_FLOW','new_session_success':any(r['case']=='new_session' and r['assessment']['passed'] for r in rows),
            'interruption':batch_error,'not_completed':len(cases)-len(rows)})
        if proc is not None:proc.terminate();proc.wait(5)
        if log is not None:log.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--knowledge',required=True);p.add_argument('--out',required=True);p.add_argument('--port',type=int,required=True);p.add_argument('--target-only',action='store_true');a=p.parse_args()
    run(a.host,Path(a.knowledge),Path(a.out),a.port,a.target_only)
