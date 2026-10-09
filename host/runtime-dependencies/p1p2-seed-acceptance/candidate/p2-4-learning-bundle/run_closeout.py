"""Freeze and run P2-only controlled acceptance. No models or old paused tasks."""
import argparse
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime,timezone
from run_real_flow import run as real_flow
from run_native_checks import phone_checks,safety_checks
from evaluation_device import adb,read_business,state,audit_delta
from device_inventory import inventory,KNOWN_FILES
from acceptance_tools import classify_backup,compare_protection,score_flow,assert_readonly_proof
from bundle_contract import need
from bundle_store import BundleStore
from learning_queries import LearningQueries
from material_graph import search_known_route
from p24deps import verify_dependencies

BASE=Path(__file__).resolve().parent;ROOT=BASE.parent
CANDIDATE=ROOT/'native-learning-candidate-v92';PREVIOUS=ROOT/'native-planning-candidate-v91'
HOSTS=['R5CW134LLBZ','emulator-5556'];PYTHON=Path(sys.executable)

def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def inputs():
    files=list(BASE.glob('*.py'))+[BASE/'DESIGN.md',BASE/'formal-plan.json',BASE/'dependency-pins.json']
    for directory in ['app/src','tests']:
        files.extend(p for p in (CANDIDATE/directory).rglob('*') if p.is_file())
    files.extend(CANDIDATE.glob('*.ps1'));files.append(CANDIDATE/'build/manual/demo-probe-debug.apk')
    return {str(p.resolve()):sha(p) for p in sorted(set(files))}

def audit_product():
    before=PREVIOUS/'app/src';after=CANDIDATE/'app/src';modified=[];added=[];unchanged=0
    for f in after.rglob('*'):
        if not f.is_file():continue
        rel=f.relative_to(after);old=before/rel
        if not old.exists():added.append(rel.as_posix())
        elif f.read_bytes()!=old.read_bytes():modified.append(rel.as_posix())
        else:unchanged+=1
    need(set(modified)=={'main/AndroidManifest.xml','main/java/edu/sydney/probe/ProbeService.java'},'UNDECLARED_PRODUCT_MODIFICATION')
    need(set(added)=={'main/java/edu/sydney/probe/'+n+'.java' for n in ['LearningAuditReceiver','LearningCapture','LearningScope']},'UNDECLARED_PRODUCT_ADDITION')
    a=(before/'main/java/edu/sydney/probe/ProbeService.java').read_text(encoding='utf-8')
    b=(after/'main/java/edu/sydney/probe/ProbeService.java').read_text(encoding='utf-8')
    need(a.splitlines()==[l for l in b.splitlines() if l.strip() not in {'LearningCapture.event(this,event);','LearningCapture.invalidate();'}],'CORE_LOGIC_DRIFT')
    a=(before/'main/AndroidManifest.xml').read_text(encoding='utf-8');b=(after/'main/AndroidManifest.xml').read_text(encoding='utf-8')
    for field in ['versionCode','versionName']:
        old=re.search(r'android:'+field+r'="([^"]+)"',a)[1]
        b=re.sub(r'android:'+field+r'="[^"]+"','android:'+field+'="'+old+'"',b,count=1)
    b='\n'.join(l for l in b.splitlines() if 'android:name=".LearningAuditReceiver"' not in l)
    need(a.splitlines()==b.splitlines(),'MANIFEST_PERMISSION_DRIFT')
    return {'verdict':'PASS','unchanged_product_files':unchanged,'modified':modified,'new':added,
            'original_semantic_skill_logic_unchanged':True,'new_permissions':0,'service_hooks_only':2}

def freeze(folder):
    folder.mkdir(parents=True,exist_ok=False)
    baseline=audit_product();write(folder/'product-diff-audit.json',baseline)
    # Correct old exec-out missing-file backups from their original bytes, never substitute current data.
    corrected=[]
    for serial in HOSTS:
        entries={path:classify_backup((BASE/'evidence/backups'/serial/path.replace('/','--')).read_bytes()) for path in KNOWN_FILES}
        corrected.append({'serial':serial,'protected_files':entries})
    write(folder/'protected-baseline-corrected.json',corrected)
    current=[inventory(s) for s in HOSTS];write(folder/'device-inventory-at-freeze.json',current)
    for old,new in zip(corrected,current):need(compare_protection(old['protected_files'],new['protected_files'])['verdict']=='PASS','BEFORE_RUN_PROTECTED_DATA_DRIFT')
    signatures={}
    for serial in HOSTS:
        for pkg in ['edu.sydney.probe','edu.sydney.transferlab','edu.sydney.parameterroom']:
            path=adb(serial,'shell','pm','path',pkg).decode('utf-8').strip().splitlines()[0].removeprefix('package:')
            need(path.startswith('/data/app/') and path.endswith('/base.apk'),'UNEXPECTED_APK_PATH')
            signatures[serial+':'+pkg]={'installed_apk_sha256':adb(serial,'shell','sha256sum',path).decode('utf-8').split()[0]}
    write(folder/'installed-apk-hashes.json',signatures)
    for pkg in ['edu.sydney.probe','edu.sydney.transferlab','edu.sydney.parameterroom']:
        need(signatures[HOSTS[0]+':'+pkg]==signatures[HOSTS[1]+':'+pkg],'DEVICE_APK_MISMATCH')
    need(signatures[HOSTS[0]+':edu.sydney.probe']['installed_apk_sha256']==sha(CANDIDATE/'build/manual/demo-probe-debug.apk'),'SOURCE_CANDIDATE_APK_MISMATCH')
    signer=subprocess.run(['powershell','-NoProfile','-Command',"& 'D:/python_code/closed-loop-gui-agent/tools/android-sdk/build-tools/34.0.0/apksigner.bat' verify --print-certs '"+str(CANDIDATE/'build/manual/demo-probe-debug.apk')+"'"],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
    need(signer.returncode==0,'APK_SIGNATURE_ERROR');(folder/'apk-signature.txt').write_text(signer.stdout+signer.stderr,encoding='utf-8')
    manifest={'frozen_at':datetime.now(timezone.utc).isoformat(),'files':inputs(),'plan':json.loads((BASE/'formal-plan.json').read_text(encoding='utf-8')),
              'evidence_channels_separate':True,'paid_model_calls':0,'old_formal_experiment_resume':False}
    write(folder/'freeze.json',manifest);return manifest

def regressions(folder):
    rows=[]
    for name,cwd,cmd in [
        ('P21_OFFLINE',ROOT/'p2-1-learning-scope',[str(PYTHON),'-X','utf8','-m','unittest','discover','-v']),
        ('P22_OFFLINE',ROOT/'p2-2-page-observation',[str(PYTHON),'-X','utf8','-m','unittest','discover','-v']),
        ('P23_OFFLINE',ROOT/'p2-3-interaction-trace',[str(PYTHON),'-X','utf8','-m','unittest','discover','-v']),
        ('P24_AND_NATIVE_ADAPTER_LOGIC',BASE,[str(PYTHON),'-X','utf8','-m','unittest','discover','-v']),
        ('PROBE_JAVA_CORE',CANDIDATE,['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(CANDIDATE/'test-core.ps1')])]:
        r=subprocess.run(cmd,cwd=cwd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
        log=r.stdout+r.stderr;(folder/(name+'.log')).write_text(log,encoding='utf-8')
        m=re.search(r'Ran (\d+) tests?',log)
        rows.append({'channel':name,'status':'PASS' if r.returncode==0 else 'FAILED','tests':int(m[1]) if m else None,
                     'java_classes':len(list((CANDIDATE/'tests').rglob('*Test.java'))) if name=='PROBE_JAVA_CORE' else None,
                     'command':cmd,'working_directory':str(cwd)})
        print(json.dumps({'regression':rows[-1]},ensure_ascii=False),flush=True)
    write(folder/'regressions.json',rows);return rows

def library_export(folder):
    library_id='p2-native-'+folder.name
    library=BASE/'libraries'/(library_id+'.sqlite');library.parent.mkdir(exist_ok=True)
    need(not library.exists(),'DO_NOT_OVERWRITE_EXISTING_LIBRARY')
    paths=sorted(folder.glob('emulator-5556-*/learning-bundle.json'))+sorted((folder/'phone-readonly').glob('*-bundle.json'))
    need(len(paths)==8,'INCOMPLETE_BUNDLE_EXPORT')
    with BundleStore(library,create=True) as store:
        for i,path in enumerate(paths):store.append(json.loads(path.read_text(encoding='utf-8')),expected_revision=i)
    before=sha(library);results=[]
    def query(*args):
        r=subprocess.run([str(PYTHON),'-X','utf8','learning_cli.py','--library-id',library_id,*args],cwd=BASE,capture_output=True,text=True,encoding='utf-8',timeout=10)
        need(r.returncode==0,'CLI_QUERY_FAILED');v=json.loads(r.stdout);results.append({'command':list(args),'result':v});return v
    pages=query('list_pages');p=pages['items'][0]['page_id'];detail=query('inspect_page',p)
    query('inspect_region',p,detail['page']['regions'][0]['region_id']);query('search_semantic_targets','--text','Back')
    need(all(r['result']['execution_authority'] is False and r['result']['implicit_observe_calls']==0 and r['result']['device_action_calls']==0 for r in results),'CLI_QUERY_AUTHORITY_ERROR')
    routes=[]
    for path in sorted(folder.glob('emulator-5556-*/learning-bundle.json')):
        b=json.loads(path.read_text(encoding='utf-8'));byhint={p['navigation_context']['page_hint']:p['page_id'] for p in b['pages']}
        route=search_known_route(b,byhint['lamp'],byhint['fan']);need(route['status']=='FOUND' and len(route['edges'])==2,'KNOWN_ROUTE_LOOKUP_FAILED')
        routes.append({'bundle_path':str(path),'route':route})
    with BundleStore(library,read_only=True) as store:
        q=LearningQueries(store);phone=[]
        for path in (folder/'phone-readonly').glob('*-bundle.json'):
            b=json.loads(path.read_text(encoding='utf-8'));phone.append(q.list_pages(b['environment']))
    need(sha(library)==before,'READONLY_CLI_CHANGED_DB')
    proof={'status':'PASS','library':str(library),'library_sha256':before,'bundles':len(paths),'fresh_process_queries':4,
           'readonly_bytes_unchanged':True,'results':results,'phone_environments':phone,'real_route_queries':routes}
    write(folder/'independent-reload-and-queries.json',proof);return proof

def complete(batch):
    folder=BASE/'evidence'/batch;manifest=freeze(folder);results=[]
    for delay in [False,True]:
        for repeat in range(1,4):results.append(real_flow('emulator-5556',batch,repeat,delay=delay))
    phone=phone_checks(folder/'phone-readonly');safety=safety_checks(folder/'pad-safety')
    rows=regressions(folder);export=None
    if all(r['status']=='PASS' for r in results) and phone['status']=='PASS':export=library_export(folder)
    after=[inventory(s) for s in HOSTS];write(folder/'device-inventory-after.json',after)
    before=json.loads((folder/'protected-baseline-corrected.json').read_text(encoding='utf-8'))
    protection=[{'serial':a['serial'],**compare_protection(b['protected_files'],a['protected_files'])} for b,a in zip(before,after)]
    write(folder/'protected-data-comparison.json',protection)
    drift={p:'MISSING' if not Path(p).exists() else sha(Path(p)) for p,h in manifest['files'].items() if not Path(p).exists() or sha(Path(p))!=h}
    write(folder/'freeze-after-check.json',{'status':'FAIL' if drift else 'PASS','frozen_files':len(manifest['files']),'drift':drift,'dependency_pins_verified':verify_dependencies()})
    verdict='PASS' if all(r['status']=='PASS' for r in results+rows) and phone['status']==safety['status']=='PASS' and all(p['verdict']=='PASS' for p in protection) and export and not drift else 'FAIL'
    scores=[]
    for s in results:
        f=Path(s['folder'])
        if s['status']=='PASS':
            a=json.loads((f/'evaluator-initial-state.json').read_text(encoding='utf-8'));b=json.loads((f/'evaluator-final-state.json').read_text(encoding='utf-8'))
            scores.append(score_flow(s,audit_delta(a,b)));assert_readonly_proof(json.loads((f/'real-query-readonly-proof.json').read_text(encoding='utf-8')))
        else:scores.append({'correct':False,'false_success':False,'reported_success':False})
    if any(not s['correct'] for s in scores):verdict='FAIL'
    summary={'scope':'P2_CONTROLLED_NATIVE_MINIMUM_LOOP_ONLY','status':verdict,'flows':results,
        'real_flow_success':sum(s['correct'] for s in scores),'real_flow_total':len(results),'independent_flow_conditions':2,'repeats_each':3,
        'real_navigation_actions':sum(s['real_navigation_actions'] for s in results),'false_success':sum(s['false_success'] for s in scores),
        'phone':phone,'safety_summary':{k:safety.get(k) for k in ['status','correct','conditions','input_calls','business_ledger_unchanged']},
        'regressions':rows,'protected_files':protection,'code_drift':drift,'library_status':export['status'] if export else 'NOT_TESTED',
        'model_calls':0,'screenshot':'NOT_TESTED_OPTIONAL_TREE_ONLY','phone_positive_navigation':'NOT_TESTED_EXISTING_USER_DRAFT',
        'autonomous_arbitrary_app_exploration':'NOT_IMPLEMENTED_OUT_OF_P2_SCOPE','P3_started':False,
        'historical_failures_preserved':True,'counts_not_generalization_guarantees':True}
    write(folder/'summary.json',summary);print(json.dumps({'final_status':verdict,'real_flows':summary['real_flow_success'],'total':len(results),'folder':str(folder)},ensure_ascii=False),flush=True)
    return verdict

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True);a=p.parse_args()
    if not a.batch.replace('-','').isalnum():raise ValueError('INVALID_BATCH')
    if complete(a.batch)!='PASS':raise SystemExit(1)
