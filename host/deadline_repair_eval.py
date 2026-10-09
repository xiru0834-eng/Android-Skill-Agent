"""Isolated current-run snapshot and structured diagnosis, never a model tool."""
import argparse, copy, hashlib, io, json, tarfile, time, uuid, zipfile
from pathlib import Path
from lab_transport import adb, HOSTS, execute
from prepare_g1 import save
from install_candidate import health
from g1_device_eval import prepare, oracle

ROOT = Path(__file__).parent
RUN = ROOT / 'evidence/flow-deadline-repair/r1'
PRIVATE = ROOT / 'private/flow-deadline-repair-r1'

def digest(data): return hashlib.sha256(data).hexdigest()

def snapshot():
    PRIVATE.mkdir(parents=True, exist_ok=False)
    inventory = {}
    with zipfile.ZipFile(PRIVATE / 'source-before.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for p in sorted(ROOT.rglob('*')):
            if p.is_file() and not any(x in p.relative_to(ROOT).parts for x in ('private','evidence','.git','__pycache__','build')):
                z.write(p, str(p.relative_to(ROOT)))
    for host in sorted(HOSTS):
        d = PRIVATE / host; d.mkdir()
        state = {'settings': {}, 'packages': {}, 'health': health(host), 'reverse': adb(host,'reverse','--list').decode()}
        if state['health'].get('final_status') != 'READY' or state['health'].get('busy'):
            raise ValueError('SERVICE_NOT_IDLE_READY: ' + host)
        for namespace,k in [('secure','enabled_accessibility_services'),('secure','accessibility_enabled'),('system','font_scale'),('system','accelerometer_rotation'),('system','user_rotation'),('global','window_animation_scale'),('global','transition_animation_scale'),('global','animator_duration_scale')]:
            state['settings'][namespace+'.'+k] = adb(host,'shell','settings','get',namespace,k).decode().strip()
        for pkg in ('edu.sydney.probe','edu.sydney.parameterroom'):
            # exec-out preserves tar bytes; no PowerShell/text/newline conversion.
            raw = adb(host,'exec-out','run-as',pkg,'tar','-cf','-','files','shared_prefs',timeout=60)
            with tarfile.open(fileobj=io.BytesIO(raw)) as tar:
                members = tar.getmembers()
                if any(m.name.startswith('/') or '..' in Path(m.name).parts for m in members): raise ValueError('UNSAFE_SNAPSHOT')
                hashes = {m.name:digest(tar.extractfile(m).read()) for m in members if m.isfile()}
            (d/(pkg+'.tar')).write_bytes(raw)
            apkpath = adb(host,'shell','pm','path',pkg).decode().strip().split(':',1)[1]
            adb(host,'pull',apkpath,str(d/(pkg+'.apk')),timeout=60)
            state['packages'][pkg] = {'tar_sha256':digest(raw),'files':hashes,'apk_sha256':digest((d/(pkg+'.apk')).read_bytes()),
                'package_dump':adb(host,'shell','dumpsys','package',pkg).decode()}
        state['display'] = {k:adb(host,'shell','wm',k).decode() for k in ('size','density')}
        save(d/'snapshot.json',state)
        inventory[host] = state
    save(RUN/'preflight/current.json',inventory)

def diagnostic(out, hosts):
    out.mkdir(parents=True,exist_ok=False)
    specs = [('E1','explicit',50,20,False),('E2','new_session',100,60,True)]
    save(out/'registered.json',{'channel':'STRUCTURED_DIAGNOSTIC','host_order':hosts,'cases':specs,'repeats':3,'model_calls':0,'launch_in_native_budget':True})
    rows=[]
    for host in hosts:
        readiness=health(host)
        save(out/(host+'-readiness.json'),{'health':readiness,'package_dump':adb(host,'shell','dumpsys','package','edu.sydney.probe').decode()})
        if readiness.get('final_status')!='READY' or readiness.get('busy'):
            raise ValueError('INITIALIZATION_NOT_IDLE_READY: '+host)
        for name,old,initial,target,fresh in specs:
            for rep in range(3):
                original=json.loads((ROOT/'evidence/g4-emulator-normal-ui-r7-default-r15'/(old+'.json')).read_text(encoding='utf-8'))
                plan=copy.deepcopy(original['ui']['selection']['plan'])
                plan['host_device_id']='host.'+host
                plan['task_id']='task.'+uuid.uuid4().hex
                previous=health(host)
                if fresh:
                    from g3_device_eval import reconnect
                    adb(host,'shell','am','force-stop','edu.sydney.probe');reconnect(host,PRIVATE/host/'snapshot.json')
                current=health(host)
                if current.get('final_status')!='READY' or current.get('busy'):
                    raise ValueError('INITIALIZATION_NOT_IDLE_READY: '+host)
                before=prepare(host,uuid.uuid4().hex,(0,initial,0,22))
                # Reproduce the normal input/confirmation foreground, not warm the target.
                adb(host,'shell','am','start','-f','0x14000000','-n','edu.sydney.probe/.MainActivity')
                start=time.monotonic();result=execute(host,plan,mode='CANDIDATE_VALIDATION');elapsed=(time.monotonic()-start)*1000
                after=oracle(host);want=copy.deepcopy(before['state']);want['bedroom_light.brightnessPercent']=target
                events=[{'property':e['property'],'value':e['value']} for e in after['events']]
                expected=[{'property':'bedroom_light.brightnessPercent','value':target}]
                success=result.get('final_status')=='SUCCESS'
                correct=after['state']==want and events==expected
                full=result.get('completed_steps')==len(plan['steps']) and result.get('final_observation_complete') is True and result.get('verification_result') is True
                timely=result.get('latency',{}).get('runtime_ms',999999)<8000
                entry=result.get('service_entry_hit') is True and result.get('flow_hash')==plan['flow_hash'] and result.get('task_id')==plan['task_id']
                row={'case':name,'rep':rep,'host':host,'channel':'STRUCTURED_DIAGNOSTIC','original_record':str(original.get('case')),'plan':plan,
                     'before':before,'after':after,'result':result,'previous_process':previous,'current_process':current,'host_elapsed_ms':elapsed,
                     'assessment':{'passed':success and correct and full and timely and entry,'wrong_action':any(e not in expected for e in events),
                       'false_success':success and not(correct and full and timely and entry),'full':full,'timely':timely,'fresh_process':not fresh or previous.get('process_session')!=current.get('process_session')}}
                save(out/(host+'-'+name+'-'+str(rep)+'.json'),row);rows.append(row)
                print(host,name,rep,result.get('final_status'),result.get('completed_steps'),result.get('latency'),row['assessment'],flush=True)
                save(out/'summary.json',{'planned':len(hosts)*6,'executed':len(rows),'passed':sum(x['assessment']['passed'] for x in rows),'model_calls':0})
                if row['assessment']['wrong_action'] or row['assessment']['false_success']: raise ValueError('SAFETY_STOP')

def install(host,apk):
    from g3_device_eval import reconnect
    state=json.loads((PRIVATE/host/'snapshot.json').read_text(encoding='utf-8'))
    if 'edu.sydney.probe/edu.sydney.probe.ProbeService' not in state['settings']['secure.enabled_accessibility_services'].split(':'):raise ValueError('NO_CURRENT_PRIOR_SERVICE_PERMISSION')
    result=adb(host,'install','-r',str(apk),timeout=60).decode()
    if 'Success' not in result:raise ValueError('INSTALL_FAILED')
    # Package replacement already stops the old process. A second immediate
    # force-stop races Android's package/service registration. These are bounded
    # installation readiness attempts, never a retry of a business task.
    attempts=[]
    for index in range(2):
        try:
            reconnect(host,PRIVATE/host/'snapshot.json');attempts.append({'attempt':index+1,'status':'READY'});break
        except ValueError as error:
            attempts.append({'attempt':index+1,'error':str(error),'health':health(host)})
            if str(error)!='REAL_SERVICE_NOT_CONNECTED' or index==1:raise
    result=health(host)
    if result.get('final_status')!='READY' or result.get('busy'):raise ValueError('SERVICE_NOT_READY')
    save(RUN/'preflight'/('installed-'+host+'-'+Path(apk).stem+'.json'),{'apk_sha256':digest(Path(apk).read_bytes()),'health':result,'permission_source':'CURRENT_RUN_SNAPSHOT','installation_readiness_attempts':attempts,'business_task_retries':0})
    print(host,'ACTUAL_SERVICE_READY',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('operation',choices=['snapshot','baseline','install']);p.add_argument('--out');p.add_argument('--apk');p.add_argument('--hosts',nargs='+',default=['emulator-5556','R5CW134LLBZ']);a=p.parse_args()
    if a.operation=='snapshot':snapshot()
    elif a.operation=='install':
        for host in a.hosts:install(host,a.apk)
    else:diagnostic(Path(a.out),a.hosts)
