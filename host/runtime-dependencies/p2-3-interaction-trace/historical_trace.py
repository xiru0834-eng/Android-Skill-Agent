"""Thin read-only legacy import. It does not create P2.2 observations or dispatch confirmations."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from p23deps import identifier, digest
from trace_contract import need, detached, SOURCES

P21 = Path('D:/Codex-deliveries/smarthome-ui-polish/p2-1-learning-scope')
PINNED_FILES = {
    'source_audit.py': '4b1a8e4293a4e7a4c629147c0822049e8c2064623b6e2a78e1c57d2dc1da11fd',
    'source-catalog.json': 'f6b21d53ae0dcc2522e8bb2bc378aebc9c3ed16e257cc64066bba01aadc84f0b'}
for name, expected in PINNED_FILES.items():
    need(hashlib.sha256((P21/name).read_bytes()).hexdigest()==expected, 'LEGACY_DEPENDENCY_CHANGED')
if 'source_audit' not in sys.modules:
    spec=importlib.util.spec_from_file_location('source_audit',P21/'source_audit.py')
    module=importlib.util.module_from_spec(spec)
    sys.modules['source_audit']=module;spec.loader.exec_module(module)
else:
    need(Path(sys.modules['source_audit'].__file__).resolve()==(P21/'source_audit.py').resolve(),
         'DEPENDENCY_NAMESPACE_CONFLICT')
from source_audit import load_catalog, audit_file
CATALOG = {v['source_id']:v for v in load_catalog()}


def _state(value):
    need(type(value) is dict and set(value)=={'page','values','saved','dirty'}
         and identifier(value['page']) and type(value['values']) is dict and type(value['saved']) is list
         and type(value['dirty']) is bool and len(value['values'])<=128 and len(value['saved'])<=128,
         'LEGACY_STATE_ERROR')
    need(all(identifier(k) and type(v) in (bool,int,float) for k,v in value['values'].items())
         and all(type(v) in (bool,int,float) for v in value['saved']), 'LEGACY_STATE_ERROR')
    return detached(value)


def adapt_legacy(value,*,source_id,sha256,evidence_ref):
    raw=detached(value)
    need(type(raw) is dict and set(raw)=={'kind','version','traceId','appPackage','appVersion','source',
                                        'goal','end','error','initial','steps','final'}
         and raw['kind']=='WORKFLOW_TRACE' and raw['version']==2 and type(raw['version']) is int,
         'LEGACY_FORMAT_ERROR')
    need(identifier(source_id) and identifier(evidence_ref) and type(sha256) is str
         and len(sha256)==64 and all(c in '0123456789abcdef' for c in sha256), 'LEGACY_SOURCE_ERROR')
    need(all(identifier(raw[k]) for k in ('traceId','appPackage','appVersion','goal','end'))
         and type(raw['error']) is str and len(raw['error'])<=240
         and raw['source'] in ('AUTOMATED','HUMAN_DECLARED'), 'LEGACY_FORMAT_ERROR')
    need(type(raw['steps']) is list and len(raw['steps'])<=128, 'LEGACY_FORMAT_ERROR')
    initial,final=_state(raw['initial']),_state(raw['final'])
    steps,edges,last=[],[],None
    actor='HUMAN_DEMONSTRATION' if raw['source']=='HUMAN_DECLARED' else 'UNKNOWN'
    for index,item in enumerate(raw['steps']):
        need(type(item) is dict and set(item)=={'id','before','eventTime','attribution','after'}
             and identifier(item['id']) and identifier(item['attribution'])
             and type(item['eventTime']) is int and item['eventTime']>=0
             and (last is None or last<=item['eventTime']), 'LEGACY_STEP_ERROR')
        pre,post=_state(item['before']),_state(item['after']);last=item['eventTime']
        changes={k:{'before':pre[k],'after':post[k]} for k in ('page','values','saved','dirty') if pre[k]!=post[k]}
        key=digest({'legacy_trace_id':raw['traceId'],'index':index,'source_digest':sha256})
        step={'interaction_id':key,'source':actor,'source_raw':raw['source'],
              'source_assurance':'LEGACY_DECLARED_NOT_AUTHENTICATED',
              'action_label':item['id'],'attribution':item['attribution'],
              'legacy_event_time':item['eventTime'],'before':pre,'after':post,
              'before_observation_id':None,'after_observation_id':None,'dispatch_id':None,
              'changes':changes,'business_audit_status':'UNAVAILABLE',
              'write_category':'OBSERVED_VIEW_OR_COMMIT_SNAPSHOT_CHANGE_NOT_JOURNAL'
                  if any(k in changes for k in ('values','saved','dirty')) else 'NO_VISIBLE_WRITE_NOT_FULL_PROOF',
              'status':'OBSERVED_HISTORICAL_LIMITED','execution_authority':False,
              'unknowns':['FULL_TREE_MISSING','DISPATCH_UNCONFIRMED','BUSINESS_JOURNAL_MISSING','CURRENT_APPROVAL_MISSING']}
        steps.append(step)
        if pre['page']!=post['page']:
            edges.append({'source_page_label':pre['page'],'target_page_label':post['page'],
                          'interaction_id':key,'status':'OBSERVED_HISTORICAL_LIMITED',
                          'source':actor,'execution_authority':False,'arrival_verified':False})
    limits=['HISTORICAL_NOT_CURRENT_CAPTURE','FULL_P22_TREE_NOT_AVAILABLE','DISPATCH_NOT_INDEPENDENTLY_CONFIRMED',
            'NO_TYPED_ENTITY_IDENTITY','NO_CURRENT_HOST_OR_UI_REVISION','NOT_NAVIGATION_SAFETY_PROOF',
            'BUSINESS_WRITES_PRESENT_NOT_AUTHORIZATION','CAPTURE_ERROR' if raw['error'] else 'NO_NEW_REAL_FLOW_TEST']
    if raw['source']=='HUMAN_DECLARED':limits.append('HUMAN_CLAIM_NOT_AUTHENTICATED')
    return detached({'kind':'HistoricalTraceMaterial','schema_version':'1.0','channel':'HISTORICAL_ANDROID_TRACE',
        'material_id':digest({'source_id':source_id,'sha256':sha256}),'source_id':source_id,
        'source_sha256':sha256,'source_ref':evidence_ref,'source_raw':raw['source'],
        'app_package':raw['appPackage'],'app_build':raw['appVersion'],'goal':raw['goal'],
        'host_device_id':None,'current_ui_revision':None,'runtime_permission':None,'capture_end':raw['end'],
        'event_clock_domain':'LEGACY_ACCESSIBILITY_EVENT_TIME_NOT_ELAPSED_PAIR',
        'initial':initial,'final':final,'interactions':steps,'observed_transitions':edges,
        'source_counts':{s:len(steps) if s==actor else 0 for s in SOURCES},
        'real_verified_edges':0,'learning_mode':'HISTORICAL_LIMITED_NOT_AUTOMATIC_LEARNING',
        'catalog_digest_verified':False,'limitations':limits,'original_trace':raw,'execution_authority':False})


def import_catalog_material(source_id):
    need(type(source_id) is str and source_id in CATALOG, 'UNKNOWN_CATALOG_SOURCE')
    spec=CATALOG[source_id]
    audit_file(spec)  # P2.1 bounded read, digest, origin, and source checks retained.
    raw=Path(spec['path']).read_bytes()
    need(len(raw)<=65536 and hashlib.sha256(raw).hexdigest()==spec['sha256'], 'MATERIAL_DIGEST_MISMATCH')
    result=adapt_legacy(json.loads(raw),source_id=source_id,sha256=spec['sha256'],evidence_ref=spec['path'])
    result['catalog_digest_verified']=True
    return result
