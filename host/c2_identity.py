"""Inert capture-time associations. Only the private lifecycle provider can seal current evidence.

Neither a client receipt nor a model assertion supplies identity authority. The
provider rereads the normal product recording and current locally reviewed data.
Queries over already built bundles do not import this provider or touch Android.
"""
import copy,json,time
from dataclasses import dataclass
from p31deps import canonical,digest,bundle_contract
from native_materials import derive_native_page,validate_native_observation

_SEAL=object()
MAX_AGE_MS=120000
def need(ok,code):
    if not ok:raise ValueError(code)

def template(observation,env):
    if env['app_package']!='edu.sydney.parameterroom' or env['app_build']!='6' or env['environment_id']!='parameter-room-u0' or env['ui_revision']!='ui.u0':return False
    markers=[n for n in observation['tree']['nodes'] if n['visible'] and n['resource_id']=='edu.sydney.parameterroom:id/psPage']
    return len(markers)==1 and markers[0]['text']=='parameter_room'

def validate_association(o,reference,*,pid,elapsed_ms):
    validate_native_observation(o);a=o.get('identity_association')
    need(type(a) is dict and a.get('schema_version')=='1.0' and a.get('producer')=='LearningIdentityReference.v1','IDENTITY_RECEIPT_REQUIRED')
    need(a.get('execution_authority') is False and a.get('source_mode')=='REFERENCE_ASSISTED' and a.get('status')=='CONFIRMED','IDENTITY_UNCONFIRMED')
    need(a.get('observation_id')==o['observation_id'] and a.get('process_session')==o['process_session']
        and a.get('window_id')==o['window_id'] and a.get('display_id')==o['display_id']
        and a.get('captured_elapsed_ms')==o['captured_elapsed_ms'],'IDENTITY_OBSERVATION_MISMATCH')
    need(type(pid) is int and a.get('process_id')==pid,'IDENTITY_PROCESS_CHANGED')
    need(0<=elapsed_ms-o['captured_elapsed_ms']<=MAX_AGE_MS,'IDENTITY_OBSERVATION_EXPIRED')
    need(template(o,reference['environment']),'IDENTITY_TEMPLATE_UNCONFIRMED')
    need(a.get('reference')==reference['receipt_reference'],'IDENTITY_REFERENCE_CHANGED')
    need(a.get('page')=='parameter_room' and o['tree']['complete'] is True,'IDENTITY_SCOPE_UNCONFIRMED')
    facts={k:v for k,v in a.items() if k not in {'association_id','observation_id','process_session','window_id','display_id','captured_elapsed_ms'}}
    last=o['attempts'][-1]
    need(last['tree_a'].get('identity_reference')==last['tree_b'].get('identity_reference')==facts,'IDENTITY_PAIR_CONFLICT')
    need(type(a.get('association_id')) is str and 1<=len(a['association_id'])<=128,'IDENTITY_ID_INVALID')
    nodes={n['node_local_id']:n for n in o['tree']['nodes']};keys=set();locals=set()
    for link in a['links']:
        key=link.get('semantic_key');need(key in reference['targets'] and key not in keys,'IDENTITY_REFERENCE_TARGET');keys.add(key)
        target=reference['targets'][key];entity,prop=key.rsplit('.',1)
        need(link.get('status')=='RESOLVED' and link.get('entity_id')==entity and link.get('property')==prop,'IDENTITY_ENTITY_CONFLICT')
        local=link.get('node_local_id');need(local in nodes and local not in locals,'IDENTITY_ELEMENT_CONFLICT');locals.add(local)
        n=nodes[local]
        need(n['resource_id']==o['app_package']+':id/'+target['id'] and n['class_name']==target['class']
            and n['role']==target['role'] and n['visible'] and n['enabled'] and not n['editable'] and not n['password'],'IDENTITY_TARGET_MISMATCH')
        need(sum(v['resource_id']==n['resource_id'] for v in nodes.values())==1,'IDENTITY_AMBIGUOUS_TARGET')
        need(link.get('strategy') in {'ID','SEMANTIC'} and link.get('matching_conditions')=='CANONICAL_RESOLVER_PAGE_ROLE_LOCAL_SCOPE_UNIQUE_AND_SAME_TREE_NODE','IDENTITY_RESOLVER_PROOF')
    need(keys==set(reference['targets']),'IDENTITY_INCOMPLETE')
    bundle_contract.sanitize_fragment(a)
    return copy.deepcopy(a)

@dataclass(frozen=True)
class IdentitySnapshot:
    _data:str
    _provider_digest:str
    _captured:float
    _seal:object
    def public(self):
        need(self._seal is _SEAL and 0<=time.monotonic()-self._captured<=120,'IDENTITY_SNAPSHOT_EXPIRED')
        return json.loads(self._data)

def capture_identity(context,observations):
    need(type(context) is dict and set(context)=={'reference','observations','pid','elapsed_ms','execution_authority'},'IDENTITY_PROVIDER_FIELDS')
    need(context['execution_authority'] is False and type(observations) is list and 1<=len(observations)<=64,'IDENTITY_PROVIDER_AUTHORITY')
    need(canonical(observations)==canonical(context['observations']),'IDENTITY_NORMAL_RECORDING_MISMATCH')
    receipts=[validate_association(o,context['reference'],pid=context['pid'],elapsed_ms=context['elapsed_ms']) for o in observations]
    data={'mode':'REFERENCE_ASSISTED','reference_sha256':context['reference']['receipt_reference']['content_sha256'],
        'reference_revision':context['reference']['receipt_reference']['revision'],
        'environment':context['reference']['environment'],'receipts':receipts,'execution_authority':False}
    stable={k:v for k,v in context.items() if k!='elapsed_ms'}
    return IdentitySnapshot(canonical(data),digest(stable),time.monotonic(),_SEAL)

def recheck_identity(snapshot,context):
    snapshot.public();current=capture_identity(context,context['observations'])
    need(current._provider_digest==snapshot._provider_digest,'IDENTITY_PROVIDER_CHANGED')

def derive_page(o,env,sid,identity_snapshot=None):
    page=derive_native_page(o,env,sid)
    if not template(o,env):return page
    page['navigation_context']['page_hint']='parameter_room';page['label']='parameter_room'
    page['limitations'].append('TEMPLATE_DOES_NOT_ESTABLISH_ENTITY')
    if identity_snapshot is None:return page
    data=identity_snapshot.public()
    need(data['environment']==env,'IDENTITY_ENVIRONMENT_MISMATCH')
    receipts=[a for a in data['receipts'] if a['observation_id']==o['observation_id']]
    need(len(receipts)==1 and receipts[0]==o.get('identity_association'),'IDENTITY_RECEIPT_NOT_SEALED')
    a=receipts[0];owners={l['node_local_id']:l['entity_id'] for l in a['links']}
    page['identity_status']='KNOWN'
    page['entities']=[{'entity_key':e,'label':e,'type':'REVIEWED_REFERENCE_ENTITY','basis':'RULE_INFERENCE','source_ids':[sid]} for e in sorted(set(owners.values()))]
    page['page_id']=digest({'environment':env,'template':page['template_id'],'entities':page['entities'],'reference_revision':data['reference_revision'],'process_session':o['process_session']})
    by_element={digest({'observation':o['observation_id'],'node':n}):e for n,e in owners.items()}
    for element in page['elements']:element['entity_key']=by_element.get(element['element_id'])
    page['limitations'].append('REFERENCE_ASSISTED_NOT_UI_ONLY_NOT_LIVE_EXECUTION_AUTHORITY')
    return page
