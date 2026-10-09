"""R3 evaluator only. No change to product contracts or sealed R1/R2 evidence."""
import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import uuid
import zipfile

from prepare_g1 import save
from repair_r3_gate import Batch, GateClosed, sha

ROOT=Path(__file__).parent
RUN=ROOT/'evidence/flow-deadline-repair/r3/20261008-r1'
PRIVATE=ROOT/'private/flow-deadline-repair-r3/20261008-r1'
HOSTS=['emulator-5556','R5CW134LLBZ']
APK=ROOT/'native/build/manual/flow-probe-v102-final-boundary.apk'
APK_HASH='c3dc23dc467f0c660dfe1919c2d79a2c19b6f78092e3227fd8b5707ae8e0f4bb'
CORES=['PortableSkillRuntime','AccessibilityBindingResolver','AccessibilityRangeExecutor','PortableSkillCodec']
LABEL='v102'


def configure(label):
    global APK,APK_HASH,LABEL
    LABEL=label
    if label=='v103':
        frozen=json.loads((RUN/'candidate-v103/freeze.json').read_text(encoding='utf-8'))
        APK=Path(frozen['apk']); APK_HASH=frozen['apk_sha256']


def gate_proved():
    gate=json.loads((RUN/'runner_gate_tests/result.json').read_text(encoding='utf-8'))
    if gate['RUNNER_STOP_GATE']!='PASS': raise ValueError('STOP_GATE_NOT_PROVED')


def snapshot():
    gate_proved()
    from lab_transport import adb, ADB
    from install_candidate import health
    from restore_deadline_repair import members
    out=RUN/'preflight'; out.mkdir(exist_ok=False)
    PRIVATE.mkdir(parents=True,exist_ok=False)
    source={}
    with zipfile.ZipFile(PRIVATE/'source-before.zip','w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob('*')):
            rel=path.relative_to(ROOT)
            if path.is_file() and not any(p in {'private','evidence','.git','__pycache__','build'} for p in rel.parts):
                source[str(rel)]=sha(path.read_bytes()); archive.write(path,str(rel))
    old=json.loads((ROOT/'evidence/flow-deadline-repair/r2/freeze-v102/freeze.json').read_text(encoding='utf-8'))
    diffs=[p for p,h in old['source'].items() if source.get(p)!=h]
    cores={name:{'current':source[str(Path('native/app/src/main/java/edu/sydney/probe')/(name+'.java'))],
        'v92':sha((ROOT.parent/'native-learning-candidate-v92/app/src/main/java/edu/sydney/probe'/(name+'.java')).read_bytes())} for name in CORES}
    for row in cores.values(): row['unchanged']=row['current']==row['v92']
    save(out/'source.json',{'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'branch':subprocess.check_output(['git','branch','--show-current'],cwd=ROOT).decode().strip(),
        'dirty':subprocess.check_output(['git','status','--short'],cwd=ROOT).decode(),
        'files':source,'r2_frozen_file_differences':diffs,'original_core':cores,
        'apk_sha256':sha(APK.read_bytes()),'apk_matches_v102':sha(APK.read_bytes())==APK_HASH})
    (out/'git-diff.patch').write_bytes(subprocess.check_output(['git','diff','--binary'],cwd=ROOT))
    if diffs or sha(APK.read_bytes())!=APK_HASH or not all(r['unchanged'] for r in cores.values()):
        raise ValueError('SOURCE_OR_V102_CANDIDATE_DRIFT')
    originals=[]
    for host in HOSTS:
        for scenario in ('E1','E2'):
            for rep in range(3):
                p=ROOT/'evidence/flow-deadline-repair/r2/diagnostic-v102'/f'{host}-{scenario}-{rep}.json'
                row=json.loads(p.read_text(encoding='utf-8'))
                originals.append({'path':str(p),'sha256':sha(p.read_bytes()),'case':scenario,'rep':rep,'host':host,
                    'plan':row['plan'],'before':row['before'],'assessment':row['assessment'],
                    'result':row['result'],'after':row['after']})
    save(out/'original-cases.json',originals)
    devices={}
    for host in HOSTS:
        folder=PRIVATE/host; folder.mkdir()
        # Capture current bytes before metadata-only status read. Never use R2 backup.
        state={'settings':{},'packages':{},'reverse':adb(host,'reverse','--list').decode(),
               'foreground':adb(host,'shell','dumpsys','activity','activities').decode(),
               'accessibility':adb(host,'shell','dumpsys','accessibility').decode(),
               'processes':adb(host,'shell','ps','-A').decode(),
               'display':{k:adb(host,'shell','wm',k).decode() for k in ('size','density')}}
        for namespace,key in [('secure','enabled_accessibility_services'),('secure','accessibility_enabled'),
                ('system','font_scale'),('system','accelerometer_rotation'),('system','user_rotation'),
                ('global','window_animation_scale'),('global','transition_animation_scale'),('global','animator_duration_scale')]:
            state['settings'][namespace+'.'+key]=adb(host,'shell','settings','get',namespace,key).decode().strip()
        for pkg in ('edu.sydney.probe','edu.sydney.parameterroom'):
            raw=adb(host,'exec-out','run-as',pkg,'tar','-cf','-','files','shared_prefs',timeout=60)
            files=members(raw); (folder/(pkg+'.tar')).write_bytes(raw)
            apkpath=adb(host,'shell','pm','path',pkg).decode().strip()
            if not apkpath.startswith('package:/data/app/') or '\n' in apkpath: raise ValueError('APK_PATH')
            apk=adb(host,'exec-out','cat',apkpath.removeprefix('package:'),timeout=60)
            (folder/(pkg+'.apk')).write_bytes(apk)
            dump=adb(host,'shell','dumpsys','package',pkg).decode()
            state['packages'][pkg]={'files':{name:sha(value) for name,value in files.items()},
                'tar_sha256':sha(raw),'apk_sha256':sha(apk),'package_dump':dump,
                'version':[s.strip() for s in dump.splitlines() if 'versionCode=' in s or 'versionName=' in s]}
            if sha((folder/(pkg+'.apk')).read_bytes())!=sha(apk) or members((folder/(pkg+'.tar')).read_bytes())!=files:
                raise ValueError('SNAPSHOT_READBACK')
        state['health']=health(host)
        save(folder/'snapshot.json',state); devices[host]=state
        save(out/'current.json',devices)
        print(host,state['packages']['edu.sydney.probe']['version'],state['health'],flush=True)
        if state['health'].get('final_status')!='READY' or state['health'].get('busy'): raise ValueError('SERVICE_NOT_IDLE_READY')
    save(out/'snapshot-check.json',{'passed':True,'hosts':HOSTS,'binary_snapshots_readback':True,
         'restore_policy':'CURRENT_R3_SNAPSHOT_NOT_R2','model_calls':0,'business_inputs':0})


def receipt(verdict, audit_path, safety=None):
    folder=Path(os.environ['R3_COMMAND_DIR'])
    # Copy the evidence to this command's namespace; no cross-run old PASS reads.
    raw=Path(audit_path).read_bytes(); (folder/'audit.json').write_bytes(raw)
    save(folder/'receipt.json',{'batch_id':os.environ['R3_BATCH_ID'],'command_id':os.environ['R3_COMMAND_ID'],
        'candidate_hash':os.environ['R3_CANDIDATE_HASH'],'verdict':verdict,
        'safety':safety or dict.fromkeys(['wrong_action','false_success','prohibited_side_effect','post_cancel_dispatch'],False),
        'audit':{'path':'audit.json','sha256':sha(raw)}})


def install_one(host):
    from lab_transport import adb
    import deadline_repair_eval as evaluation
    evaluation.RUN=RUN; evaluation.PRIVATE=PRIVATE
    evaluation.install(host,APK)
    rawpath=adb(host,'shell','pm','path','edu.sydney.probe').decode().strip().removeprefix('package:')
    actual=sha(adb(host,'exec-out','cat',rawpath,timeout=60))
    if actual!=APK_HASH: raise ValueError('ACTUAL_INSTALLED_APK_MISMATCH')
    path=RUN/'preflight'/('installed-'+host+'-'+APK.stem+'.json')
    data=json.loads(path.read_text(encoding='utf-8')); data['actual_installed_apk_sha256']=actual
    save(path,data); receipt('PASS',path)


def prepare(host, case, initial):
    from lab_transport import adb
    from g1_device_eval import oracle
    started=time.monotonic()
    adb(host,'shell','am','start','-n','edu.sydney.parameterroom/.ParameterRoomActivity',
        '--es','initial',','.join(map(str,initial)),'--es','caseId',case,'--es','fault','normal','--ei','commitDelayMs','0')
    latest=None
    while time.monotonic()-started<12:
        latest=oracle(host)
        if latest['case_id']==case and latest['initial']==list(initial) and not latest['events']: return latest
        time.sleep(.1)
    raise ValueError('INITIALIZATION_FAILED')


def case_one(host, scenario, rep):
    from lab_transport import adb, execute
    from install_candidate import health
    from g3_device_eval import reconnect
    from g1_device_eval import oracle
    key=f'{host}-{scenario}-{rep}'
    out=RUN/('reproduction-'+LABEL); out.mkdir(exist_ok=True)
    original_path=ROOT/'evidence/flow-deadline-repair/r2/diagnostic-v102'/(key+'.json')
    original=json.loads(original_path.read_text(encoding='utf-8'))
    plan=copy.deepcopy(original['plan']); plan['task_id']='task.'+uuid.uuid4().hex
    plan['host_device_id']='host.'+host
    initial=50 if scenario=='E1' else 100; target=20 if scenario=='E1' else 60
    previous=health(host)
    if scenario=='E2':
        adb(host,'shell','am','force-stop','edu.sydney.probe'); reconnect(host,PRIVATE/host/'snapshot.json')
    current=health(host)
    if current.get('final_status')!='READY' or current.get('busy'): raise ValueError('SERVICE_NOT_IDLE_READY')
    before=prepare(host,'r3.'+uuid.uuid4().hex,(0,initial,0,22))
    adb(host,'shell','am','start','-f','0x14000000','-n','edu.sydney.probe/.MainActivity')
    foreground=adb(host,'shell','dumpsys','activity','activities').decode()
    processes=adb(host,'shell','ps','-A').decode()
    wall_start=time.monotonic_ns()
    result=execute(host,plan,mode='CANDIDATE_VALIDATION')
    wall_end=time.monotonic_ns()
    after=oracle(host)
    expected=[{'property':'bedroom_light.brightnessPercent','value':target}]
    events=[{'property':e['property'],'value':e['value']} for e in after['events']]
    truth=copy.deepcopy(before['state']); truth['bedroom_light.brightnessPercent']=target
    success=result.get('final_status') in {'SUCCESS','NO_ACTION_REQUIRED'}
    identity=result.get('service_entry_hit') is True and result.get('flow_hash')==plan['flow_hash'] and result.get('task_id')==plan['task_id']
    full=result.get('completed_steps')==4 and result.get('final_observation_complete') is True and result.get('verification_result') is True
    timely=isinstance(result.get('latency',{}).get('runtime_ms'),(int,float)) and result['latency']['runtime_ms']<8000
    correct=after['state']==truth and events==expected
    protected=all(after['state'][k]==before['state'][k] for k in before['state'] if k!='bedroom_light.brightnessPercent')
    wrong=not protected or any(e not in expected for e in events)
    false=success and not(identity and full and timely and correct)
    audit_complete=(before.get('case_id')==after.get('case_id') and isinstance(after.get('events'),list)
        and result.get('request_id') is not None and identity and isinstance(result.get('execution_actions'),list)
        and isinstance(result.get('observations'),list) and isinstance(result.get('completion_boundary'),dict))
    passed=success and identity and full and timely and correct
    fresh=scenario!='E2' or previous.get('process_session')!=current.get('process_session')
    passed=passed and fresh
    assessment={'passed':passed,'wrong_action':wrong,'false_success':false,'audit_complete':audit_complete,
                'full':full,'timely':timely,'entry':identity,'fresh_process':fresh}
    row={'case':scenario,'rep':rep,'host':host,'channel':'STRUCTURED_NORMAL_ENTRY_DIAGNOSTIC',
        'candidate_apk_sha256':APK_HASH,'source_evidence':str(original_path),'source_evidence_sha256':sha(original_path.read_bytes()),
        'plan':plan,'before':before,'after':after,'result':result,'assessment':assessment,
        'previous_process':previous,'current_process':current,'foreground_before':foreground,'processes_before':processes,
        'evaluator_wall':{'clock':'HOST_MONOTONIC_NS','start':wall_start,'end':wall_end,'duration_ms':(wall_end-wall_start)/1e6},
        'model_calls':0,'setup_actions':'EVALUATOR_UI_ACTION','target_is_cold_start_claim':False}
    path=out/(key+'.json'); save(path,row)
    print(key,result.get('final_status'),result.get('latency'),assessment,flush=True)
    if wrong or false:
        receipt('SAFETY_STOP',path,{'wrong_action':wrong,'false_success':false,'prohibited_side_effect':not protected,'post_cancel_dispatch':False})
    elif not audit_complete:
        raise ValueError('AUDIT_INCOMPLETE')
    elif passed:
        receipt('PASS',path)
    elif result.get('final_status')=='BUDGET_EXCEEDED' and not result.get('verification_result'):
        receipt('DIAGNOSTIC_TIMEOUT',path)
    else:
        receipt('UNREGISTERED_FAILURE',path)


def reproduce():
    gate_proved()
    if not json.loads((RUN/'preflight/snapshot-check.json').read_text())['passed']: raise ValueError('NO_CURRENT_SNAPSHOT')
    specs=[]
    for host in HOSTS: specs.append({'id':'install-'+host,'kind':'device','accept':['PASS'], 'argv':[sys.executable,'-X','utf8',__file__,'install_one','--host',host,'--label',LABEL]})
    for host in HOSTS:
        for scenario in ('E1','E2'):
            for rep in range(3):
                specs.append({'id':f'{host}-{scenario}-{rep}','kind':'diagnostic','accept':['PASS','DIAGNOSTIC_TIMEOUT'],
                    'argv':[sys.executable,'-X','utf8',__file__,'case_one','--host',host,'--scenario',scenario,'--rep',str(rep),'--label',LABEL]})
    # A failed diagnostic cannot dispatch these downstream tasks even if a
    # caller ignores this function's exit code and tries their command IDs.
    for name,kind in [('g1','device'),('cancel','device'),('real-nl','model')]:
        specs.append({'id':name,'kind':kind,'accept':['PASS'],'argv':[]})
    for spec in specs:
        spec['argv_sha256']=sha(json.dumps(spec['argv']).encode())
        spec['source_files']={str(ROOT/name):sha((ROOT/name).read_bytes()) for name in ['repair_r3.py','repair_r3_gate.py','lab_transport.py']}
    batch=Batch.create(RUN/('runner' if LABEL=='v102' else 'runner-'+LABEL),'r3-20261008-r1-'+LABEL,APK_HASH,specs)
    save(RUN/('manifest.json' if LABEL=='v102' else 'manifest-'+LABEL+'.json'),{'scope':'R3_NORMAL_ENTRY_DIAGNOSIS_REGISTERED_BLOCK','candidate':APK_HASH,
        'native_budget_ms':8000,'real_model_calls':0,'registered_commands':specs,'inter_case_rule':'sequential; wait for idle health; no retries',
        'counts':{'structured_initial':12,'structured_total_cap':60,'device_business_total_cap':98,'model_attempt_cap':32,'model_estimated_usd_cap':1},
        'max_performance_repair_rounds':2,'restore_policy':'CURRENT_R3_SNAPSHOT'})
    try:
        for spec in specs[:14]:
            batch.run(spec['id'],spec['argv'],timeout=90 if spec['id'].startswith('install') else 55,cwd=ROOT)
            print('ACCEPTED',spec['id'],flush=True)
    except GateClosed:
        # Recovery is not a new task. Issue only the existing product cancel
        # channel for this run's devices, then stop (no G1/model fall-through).
        from lab_transport import cancel
        for host in HOSTS:
            try: cancel(host)
            except Exception as error: print('CANCEL_ERROR',host,type(error).__name__,flush=True)
        raise
    state=batch.state()
    save(RUN/('reproduction-'+LABEL)/'summary.json',{'planned':12,'performance_failed':state['performance_failed'],
        'diagnostic_status':'DIAGNOSTIC_COMPLETE_PERFORMANCE_FAIL' if state['performance_failed'] else 'DIAGNOSTIC_COMPLETE',
        'formal_gate_open':not state['performance_failed'],'model_calls':0})
    print('DIAGNOSTIC_FINISHED',state,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('operation',choices=['snapshot','reproduce','install_one','case_one'])
    parser.add_argument('--host',choices=HOSTS); parser.add_argument('--scenario',choices=['E1','E2']); parser.add_argument('--rep',type=int)
    parser.add_argument('--label',choices=['v102','v103'],default='v102')
    args=parser.parse_args()
    configure(args.label)
    if args.operation=='case_one': case_one(args.host,args.scenario,args.rep)
    elif args.operation=='install_one': install_one(args.host)
    else: globals()[args.operation]()
