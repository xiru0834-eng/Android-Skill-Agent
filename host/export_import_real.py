"""Actual G2 formal source -> reused P51/P52 v2 inert transport -> actual target stage."""
import copy,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'store'));sys.path.insert(0,str(ROOT/'transport'))
from device_knowledge import KnowledgeLibrary
from device_deps import records,compiler,digest
from device_bundle import write_bundle
from device_safe_import import read_path,read_archive,SourcePolicy
from device_catalog import Catalog
from make_native_knowledge import build
from prepare_g1 import save
from lab_transport import adb

def run(out):
    out.mkdir(parents=True,exist_ok=False)
    library=KnowledgeLibrary.open(ROOT/'private/source-library-v2-r2',approved_roots=[ROOT/'evidence'])
    try:
        rows=library.list_knowledge('FORMAL')
        if len(rows)!=1:raise ValueError('REAL_PUBLISHED_SOURCE_REQUIRED')
        source=rows[0];envelope=library.export(source['key'])
        if digest({k:v for k,v in envelope.items() if k!='digest'})!=envelope['digest']:raise ValueError('SOURCE_EXPORT_DIGEST')
    finally:library.close()
    docs={'flow.json':copy.deepcopy(source['flow'])};package=copy.deepcopy(source['package'])
    for i,e in enumerate(package['evidence']):
        ref='evidence/reference-%03d.json'%i
        docs[ref]={'id':e['id'],'kind':e['kind'],'summary':e['description'],'source_reference_sha256':digest(e)}
        e['ref']=ref
    profile=records.environment.audited_room_profile().to_dict() if hasattr(records,'environment') else None
    # P33 audit is public, fixed and independently used by the original compiler.
    from device_deps import verify_predecessor
    from p34deps import p33
    profile=p33.environment.audited_room_profile().to_dict()
    caps=source['flow']['dependencies']['capabilities']
    docs['environment.json']=package
    docs['dependencies.json']={'declared':source['flow']['dependencies'],'controller_profiles':{
        k:v for k,v in profile['targets'].items() if v['skill'] in caps},'profile_scope':'SOURCE_AUDIT_NOT_CURRENT_DEVICE','native_flow_read_adapter':True}
    docs['knowledge.json']={'source_mode':'REAL_MODEL_CANDIDATE','generation_channel':'REAL_GPT',
        'model_calls':source['supplement']['model_cost']['calls'],'reported_usd':None,
        'human_revisions':[{'type':'DOCUMENTATION_AND_FORMAT_METADATA_REVIEW','added_read_dependency':'SetPower','extra_business_calls':0}],
        'validation_points':[{'inputs':p['inputs'],'channel':p['channel'],'setting_trial':p['setting_trial'],
                              'device_execution_verified':p['device_execution_verified'],'parameter_domain_verified':False} for p in source['eligible_points']],
        'learning_materials_status':'PUBLIC_TREE_SOURCES_SUMMARIZED_NO_PIXELS_OR_LIVE_NODES',
        'failure_history':[{'kind':'ORIGINAL_MODEL_STATIC_REJECTION','count':2}],
        'limitations':source['supplement']['limitations'],'execution_authority':False}
    docs['scope.json']={'channel':'DEVICE_VALIDATED_KNOWLEDGE','formal_retrievable':False,'execution_authority':False,
        'verified_environments':[package['environment']],'source_version_sha256':source['version_sha256'],
        'source_envelope_digest':envelope['digest'],
        'semantic_slots':[{'name':x['name'],'requires_target_resolution':True} for x in source['flow']['inputs'] if x['type']=='entity'],
        'source_instance_scope':{'account_scope':'EXPERIMENT_NO_ACCOUNT','site_scope':'PARAMETER_ROOM_LOCAL_STATE','cross_user_identity_guaranteed':False},
        'source_publication_is_history_not_target_authority':True}
    docs['description.json']={'purpose':source['flow']['purpose'],'notice':'Source-published knowledge, inert on target. Local review and new task confirmation required.'}
    archive=out/'published-brightness-v1.zip'
    exported=write_bundle(archive,docs,package_id='real.bedroom-light-brightness',version=source['flow']['version'],
        app={'package':package['environment']['app_package'],'version':package['environment']['app_version']})
    save(out/'export.json',{**exported,'source_key':source['key'],'source_flow_hash':digest(source['flow']),
        'source_published':True,'original_module_extension':'P51_P52_VERSIONED_ANDROID_V2','source_permission_copied':False})
    verified=read_path(archive)
    target='emulator-5556';catalog=Catalog(ROOT/'private/target-library-p52-v2')
    policy=SourcePolicy({verified.sha256:'current-source-experimental-phone'})
    imported=catalog.import_bytes('source-phone',verified.raw,policy,expected_revision=0)
    reloaded=catalog.load('source-phone',verified.manifest()['package_id'],verified.manifest()['version'])
    if reloaded.documents()['flow.json']!=source['flow']:raise ValueError('FLOW_CHANGED_DURING_TRANSFER')
    target_version=adb(target,'shell','dumpsys','package','edu.sydney.parameterroom').decode()
    if 'versionName='+package['environment']['app_version'] not in target_version:raise ValueError('TARGET_APP_VERSION_MISMATCH')
    save(out/'import.json',{**imported,'target_host':target,'same_flow':True,'entity_confirmation':'EXPERIMENT_NO_ACCOUNT_SAME_DECLARED_ENTITY_IDS_PENDING_NATIVE_REVIEW',
        're_demonstration':0,'flow_modification':0,'manual_binding':0,'source_approval_copied':False})
    task=json.loads((ROOT/'evidence/g2-reviewed-r2/task.json').read_text(encoding='utf-8'));task['host_device_id']='host.'+target
    publication={'version_sha256':source['version_sha256'],'eligible_points':[{'inputs':p['inputs']} for p in source['eligible_points']]}
    native=build(reloaded.documents()['flow.json'],reloaded.documents()['environment.json'],task,publication)
    save(out/'target-native-knowledge.json',native)
    adb(target,'shell','run-as','edu.sydney.probe','sh','-c',"'cat > files/published-flow-incoming.json'",input=json.dumps(native,ensure_ascii=False).encode())
    save(out/'target-stage.json',{'target_host':target,'archive_sha256':verified.sha256,'native_flow_hash':native['flow_hash'],
        'local_review':'NOT_YET_GRANTED','execution_authority':False,'source_raw_flow_unchanged':True})
if __name__=='__main__':run(Path(sys.argv[1]))
