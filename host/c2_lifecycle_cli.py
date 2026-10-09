"""Private fixed worker. No HTTP listener, model, oracle or device input command."""
import argparse,hashlib,json,re,sys
from pathlib import Path
from c2_validation import CandidateService,compiler,need
from c2_inbox import DraftInbox
from lab_transport import adb,HOSTS

def deployed_package(host):
    import xml.etree.ElementTree as ET
    raw=adb(host,'shell','run-as','edu.sydney.probe','cat','files/portable-approved.json')
    profile=compiler.audited_room_profile().to_dict()
    need(hashlib.sha256(raw).hexdigest()==profile['source_package_sha256'],'CURRENT_PACKAGE_MISMATCH')
    prefs=ET.fromstring(adb(host,'shell','run-as','edu.sydney.probe','cat','shared_prefs/portable_approval.xml'))
    local_hash=next((e.text for e in prefs if e.attrib.get('name')=='hash'),None)
    need(local_hash==hashlib.sha256(raw).hexdigest(),'LOCAL_PACKAGE_REVIEW_REQUIRED')
    approved=json.loads(raw)
    return {'kind':'AppKnowledgePackage','schema_version':'1.0','id':'package.c2_assisted','version':'1.0.0',
        'flow_refs':[{'id':'flow.c2_pending','version':'1.0.0'}],'environment':profile['environment'],
        'entities':[{'entity_id':e['device'],'capabilities':[c['skill'] for c in e['capabilities']]} for e in approved['catalog']],
        'bindings':[],'documentation_refs':[],
        'evidence':[{'id':'current.local.catalog','kind':'AUDIT_REFERENCE',
            'ref':'sha256:'+hashlib.sha256(raw).hexdigest(),
            'description':'Exact current locally reviewed catalog bytes; reference only, not copied execution authority'}],
        'unknowns':[]}

def public_context(host):
    package=deployed_package(host)
    probe=adb(host,'shell','dumpsys','package','edu.sydney.probe').decode()
    app=adb(host,'shell','dumpsys','package','edu.sydney.parameterroom').decode()
    profiles={'107':('0.69-c2-candidate','demo-probe-c2-r2-v107-final.apk'),'108':('0.70-identity-evidence','demo-probe-c2-identity-v108.apk'),'109':('0.71-service-audit','demo-probe-service-audit-v109.apk')}
    versions=[code for code,(name,_) in profiles.items() if 'versionCode='+code+' ' in probe and 'versionName='+name in probe]
    need(len(versions)==1,'CURRENT_PROBE_REQUIRED');code=versions[0]
    need('versionCode=6 ' in app and 'versionName=0.8-parameter-room' in app,'CURRENT_APP_REQUIRED')
    path=adb(host,'shell','pm','path','edu.sydney.probe').decode().strip()
    need(path.startswith('package:/data/app/') and '\n' not in path,'APK_PATH')
    actual=hashlib.sha256(adb(host,'exec-out','cat',path.removeprefix('package:'))).hexdigest()
    # This Python overlay has no rebuilt Android binary. Pin the original exact
    # release artifact, not a fictitious APK under this new source directory.
    built=Path(__file__).resolve().parent/'native/build/manual'/profiles[code][1]
    from c2_runtime_request import PROBE107_SHA256,PROBE108_SHA256,PROBE109_SHA256
    need(built.is_file() and hashlib.sha256(built.read_bytes()).hexdigest()=={'107':PROBE107_SHA256,'108':PROBE108_SHA256,'109':PROBE109_SHA256}[code],'PINNED_PROBE_ARTIFACT_CHANGED')
    need(built.is_file() and hashlib.sha256(built.read_bytes()).hexdigest()==actual,'EXACT_INSTALLED_PROBE_REQUIRED')
    profile=compiler.audited_room_profile().to_dict()
    public=[]
    for key,t in sorted(profile['targets'].items()):
        public.append({'entity_id':t['entity_id'],'skill':t['skill'],'domain':t['domain'],'unit':t['unit'],'property':key.split('.',1)[1]})
    text=('Current deployed public contract v1: Android Parameter Room versionCode 6 corresponds to versionName 0.8-parameter-room, UI u0. '
          'The installed Probe code'+code+' APK digest matches this frozen build. It implements semantic_state_read_v1 through the normal candidate entrance. '
          'The allowed_capabilities PINNED_SOURCE_SUPPORTED_SUBSET_NOT_LIVE_APPROVAL/native_flow_read_adapter=false flag describes an older pinned source audit, not this installed native adapter. '
          'Current locally approved semantic catalog: '+json.dumps(public,ensure_ascii=False,separators=(',',':'))+'. '
          'Each operation sets only its named property, uses an explicit user parameter, and is an absolute idempotent setter with direct submission (no separate Save). '
          'The frozen native runtime checks current App/window, uniquely resolves the locally reviewed semantic binding, freshly reads public state, checks each effect and preserves unmentioned properties. '
          'This public contract does not assert a current UI identity or grant execution authority. Current target identity and local approval must be checked at execution; a model name cannot create an entity. '
          'No parameter point or whole domain has been device-validated merely by this document. Unknown business requirements must remain unknown. '
          'Flow contract terminology: BLOCKS_EXECUTION denotes unresolved information required to compile and validate the reusable business definition. '
          'Future runtime admission is a separate known mechanism: the existing UserCandidateActivity requires an explicit preview confirmation; '
          'CandidateService compiles the task against the current locally approved package; the native runner re-observes and uniquely resolves current targets and enforces all original window, focus, overlay, deadline and cancellation checks. '
          'Those required checks are not missing business facts and no check is bypassed. Their future satisfaction is not asserted at learning time; a failed check safely rejects that particular invocation. '
          'The reusable draft therefore never carries permission. Unsupported guards or genuinely unresolved entity/property/parameter/business semantics still block the definition. '
          'This is a description of the current product interfaces, not a user instruction or authority grant.')
    return {'environment':{'app_package':'edu.sydney.parameterroom','app_build':'6','environment_id':'parameter-room-u0','ui_revision':'ui.u0','domain':'EXPERIMENT_APP'},
        'probe_apk_sha256':actual,'app_version_code':'6','app_version_name':'0.8-parameter-room','document':text,'execution_authority':False}

def identity_context(host):
    """Fixed read-only product source, not an evaluator-provided success receipt."""
    import datetime
    from c2_runtime_request import PROBE108_SHA256,PROBE109_SHA256
    context=public_context(host);need(context['probe_apk_sha256'] in {PROBE108_SHA256,PROBE109_SHA256},'IDENTITY_BUILD_UNSUPPORTED')
    # Approval was checked above; reread before/after the normal recording to reject revocation/races.
    deployed_package(host)
    raw=adb(host,'shell','run-as','edu.sydney.probe','cat','files/portable-approved.json');approved=json.loads(raw)
    recording=json.loads(adb(host,'shell','run-as','edu.sydney.probe','cat','files/c2-recording.json'))
    need(recording.get('state')=='STOPPED' and recording.get('last_capture_error') is None,'IDENTITY_RECORDING_INCOMPLETE')
    observations=recording['observations'];need(0<len(observations)<=64,'IDENTITY_RECORDING_EMPTY')
    def modified(path):
        text=adb(host,'shell','run-as','edu.sydney.probe','stat','-c','%y',path).decode().strip()
        return int(datetime.datetime.fromisoformat(text).timestamp()*1000)
    content=hashlib.sha256(raw).hexdigest()
    revision=content+':'+str(modified('files/portable-approved.json'))+':'+str(modified('shared_prefs/portable_approval.xml'))
    pid=adb(host,'shell','pidof','edu.sydney.probe').decode().strip();need(re.fullmatch('[0-9]+',pid) is not None,'IDENTITY_PROCESS_UNAVAILABLE')
    elapsed=int(float(adb(host,'shell','cat','/proc/uptime').decode().split()[0])*1000)
    deployed_package(host)
    need(raw==adb(host,'shell','run-as','edu.sydney.probe','cat','files/portable-approved.json'),'IDENTITY_REFERENCE_CHANGED')
    need(revision==content+':'+str(modified('files/portable-approved.json'))+':'+str(modified('shared_prefs/portable_approval.xml')),'IDENTITY_REFERENCE_CHANGED')
    return {'reference':{'environment':context['environment'],'targets':approved['bindings'],
        'receipt_reference':{'content_sha256':content,'revision':revision,'approval_provenance':'CURRENT_LOCAL_PORTABLE_SKILL_STORE_HASH_CHECK',
            'app_package':context['environment']['app_package'],'app_version':context['app_version_name'],'app_build':6,'scope':'parameter-room-u0.EXPERIMENT_APP'}},
        'observations':observations,'pid':int(pid),'elapsed_ms':elapsed,'execution_authority':False}

def verify_current_published(root,knowledge):
    from c2_validation import KnowledgeLibrary,canonical
    from make_native_knowledge import build
    library=Path(root)/'lifecycle/knowledge'
    need((library/KnowledgeLibrary.FILENAME).is_file(),'FORMAL_FLOW_NOT_AVAILABLE')
    lib=KnowledgeLibrary.open(library,approved_roots=[Path(root)/'lifecycle'])
    try:
        rows=[r for r in lib.list_knowledge('FORMAL') if r['version_sha256']==knowledge.get('source_publication')]
        need(len(rows)==1,'FORMAL_FLOW_NOT_AVAILABLE');row=rows[0]
        need(knowledge.get('flow')==row['flow'] and knowledge.get('package')==row['package'],'FORMAL_SOURCE_CHANGED')
        # Rebuild the ENTIRE envelope, not just its self-reported publication/hash.
        expected=build(row['flow'],row['package'],knowledge['task_template'],row)
        expected['source_origin']='REAL_MODEL_ASSISTED_C2_WITH_AUDITED_PROGRAM_NORMALIZATION'
        expected['display_name']=knowledge.get('display_name')  # label is not identity or authority
        need(canonical(expected)==canonical(knowledge),'FORMAL_ENVELOPE_CHANGED')
    finally:lib.close()
    return knowledge

def current_published(root,host):
    import xml.etree.ElementTree as ET
    raw=adb(host,'shell','run-as','edu.sydney.probe','cat','files/published-flow-local.json')
    need(len(raw)<=131072,'KNOWLEDGE_SIZE_LIMIT')
    prefs=ET.fromstring(adb(host,'shell','run-as','edu.sydney.probe','cat','shared_prefs/flow_knowledge_review.xml'))
    approved=next((e.text for e in prefs if e.attrib.get('name')=='raw_sha256'),None)
    need(hashlib.sha256(raw).hexdigest()==approved,'LOCAL_FLOW_REVIEW_REQUIRED')
    return verify_current_published(root,json.loads(raw))

def run(root,host,body):
    need(host in HOSTS,'UNKNOWN_HOST')
    need(type(body) is dict and set(body)=={'operation','candidate_id','payload'},'REQUEST_FIELDS')
    id=body['candidate_id'];op=body['operation'];p=body['payload'];need(type(p) is dict,'REQUEST_FIELDS')
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    # Separate fixed lock file: all workers serialize across restarts/processes.
    import msvcrt
    with (root/'worker.lock').open('a+b') as lock:
        if lock.tell()==0:lock.write(b'0');lock.flush()
        lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        try:
            if op=='public_context' and p=={}:return public_context(host)
            if op=='identity_context' and p=={}:return identity_context(host)
            if op=='current_published' and p=={}:return current_published(root,host)
            c=CandidateService(root/'lifecycle',DraftInbox(root/'candidates.sqlite'),'host.'+host.lower(),deployed_package(host),
                receipt_reader=lambda attempt:json.loads(adb(host,'shell','run-as','edu.sydney.probe','cat','files/c2-validation-'+attempt+'.json')))
            if op=='prepare_validation' and set(p)=={'inputs'}:return c.prepare(id,p['inputs'])
            if op=='finish_validation' and set(p)=={'attempt_id'}:return c.finish(id,p['attempt_id'])
            if op=='cancel_validation' and set(p)=={'attempt_id'}:return c.cancel(id,p['attempt_id'])
            if op=='validation_status' and p=={}:return c.inspect(id)
            if op=='publish' and set(p)=={'confirmed'}:return c.publish(id,confirmed=p['confirmed'])
            if op=='published' and p=={}:return c.published(id)
            if op=='candidate_details' and p=={}:return c.details(id)
            raise ValueError('REQUEST_FIELDS')
        finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('--host',required=True);a=p.parse_args()
    try:
        data=sys.stdin.buffer.read(1048577);need(len(data)<=1048576,'INPUT_LIMIT')
        result=run(a.root,a.host,json.loads(data));sys.stdout.buffer.write(json.dumps(result,ensure_ascii=False).encode())
    except Exception as e:
        code=str(getattr(e,'code',str(e)));code=code if re.fullmatch('[A-Z_]{1,128}',code) else 'LIFECYCLE_UNAVAILABLE'
        print(json.dumps({'error':code}));sys.exit(1)
