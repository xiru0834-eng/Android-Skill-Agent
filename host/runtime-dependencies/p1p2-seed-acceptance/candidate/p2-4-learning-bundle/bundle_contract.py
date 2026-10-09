"""Inert, bounded learning material; provenance is not an input authorization."""
import json
import math
import re
import uuid

from p24deps import canonical, digest

BASIS = {'OBSERVATION_FACT','DOCUMENTATION_STATEMENT','HUMAN_CONFIRMATION',
         'RULE_INFERENCE','MODEL_HYPOTHESIS','UNKNOWN'}
MAX_BUNDLE_BYTES = 2 * 1024 * 1024
FORBIDDEN = {'oracle','hidden_locators','hidden_route','test_answers','truth_state',
             'input_permission','input_permit','action_permit','scope_authorization',
             'binder','resolved_node','accessibilitynode','gesture_closure','run_as'}
SENSITIVE = {'password','secret','api_key','token','authorization','credential'}


class BundleError(ValueError):
    pass


def need(condition, code):
    if not condition: raise BundleError(code)


def key(value):
    need(type(value) is str and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',value) is not None
         and '..' not in value and not re.match(r'^[A-Za-z]:',value), 'INVALID_ID')
    return value


def environment(value):
    need(type(value) is dict and set(value)=={'app_package','app_build','environment_id','ui_revision','domain'},
         'INVALID_ENVIRONMENT')
    for name,item in value.items():
        if name in ('app_build','ui_revision') and item is None: continue
        key(item)
    return dict(value)


def sanitize_fragment(value, depth=0):
    need(depth<=64,'MATERIAL_DEPTH_LIMIT')
    if type(value) is dict:
        need(len(value)<=2048 and all(type(k) is str for k in value),'INVALID_MATERIAL')
        out={}
        for k,v in value.items():
            need(k.casefold() not in FORBIDDEN,'FORBIDDEN_MATERIAL')
            if k=='execution_authority': need(v is False,'AUTHORITY_IN_MATERIAL')
            metadata_flag=k.casefold()=='password' and type(v) is bool
            out[k]='[REDACTED]' if k.casefold() in SENSITIVE and not metadata_flag else sanitize_fragment(v,depth+1)
        return out
    if type(value) is list:
        need(len(value)<=4096,'MATERIAL_SIZE_LIMIT')
        return [sanitize_fragment(v,depth+1) for v in value]
    if type(value) is str:
        need(len(value)<=4096,'MATERIAL_TEXT_LIMIT')
        value=re.sub(r'(?i)\bsk-[A-Za-z0-9_\-]{12,}','[REDACTED_KEY]',value)
        value=re.sub(r'(?i)\bBearer\s+\S+','[REDACTED_CREDENTIAL]',value)
        value=re.sub(r'\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b','[REDACTED_CONTACT]',value)
        # Do not rewrite opaque IDs/digests whose internal digits happen to resemble a phone.
        # Chinese prose adjacent to a standalone phone still redacts.
        value=re.sub(r'(?<![A-Za-z0-9_])(?:\+?86[- ]?)?1[3-9]\d{9}(?![A-Za-z0-9_])','[REDACTED_CONTACT]',value)
        value=re.sub(r'(?i)(?:[A-Z]:[\\/]|file://|\\\\)[^\s\"<>]+','[REDACTED_PATH]',value)
        return re.sub(r'(?<![\w:])/(?:home|tmp|var|data|Users|mnt|etc)/[^\s\"<>]+','[REDACTED_PATH]',value)
    need(value is None or type(value) in (int,bool,float),'NON_JSON_MATERIAL')
    if type(value) is float:need(math.isfinite(value),'INVALID_NUMBER')
    return value


def make_source(source_id,channel,fragment,*,basis,grade,source_digest=None,capture=None,limitations=None):
    safe=sanitize_fragment(fragment)
    return {'source_id':key(source_id),'channel':key(channel),'basis':basis,'evidence_grade':key(grade),
            'source_digest':source_digest,'fragment_digest':digest(safe),'fragment_id':digest({'source':source_id,'fragment':safe}),
            'fragment':safe,'integrity':'CONTENT_DIGEST_ONLY_NOT_AUTHENTICATED','capture':capture,
            'limitations':list(limitations or []),'untrusted_data':True,'execution_authority':False}


def claim(text,basis,source_ids,*,page_ids=None,topic='SUMMARY'):
    safe=sanitize_fragment(text)
    return {'claim_id':digest({'text':safe,'basis':basis,'sources':source_ids,'pages':page_ids or []}),
            'text':safe,'basis':basis,'source_ids':list(source_ids),'page_ids':list(page_ids or []),'topic':key(topic)}


def make_bundle(env,*,mode):
    return {'kind':'LearningBundle','schema_version':'1.0','bundle_id':str(uuid.uuid4()),'environment':environment(env),
            'scope_summary':{'learning_mode':key(mode),'known_range':[],'limitations':[],
                             'authorization_status':'MATERIAL_ONLY_NO_EXECUTION'},
            'sources':[],'pages':[],'claims':[],'interactions':[],'navigation':[],'documents':[],
            'unknowns':[],'human_participation':[], 'execution_authority':False,
            'model_upload_authorized':False,'current_ui_confirmed':False}


def refs(value, known):
    need(type(value) is list and len(value)<=256 and len(value)==len(set(value)), 'INVALID_REFERENCE')
    need(all(type(v) is str and v in known for v in value),'BROKEN_REFERENCE')


def _check_inert_real_trace(t,sources,pages):
    """Validate imported inert proof links, not trust or restore input authority."""
    traces=[sources[s]['fragment'] for s in t['source_ids'] if sources[s]['channel']=='REAL_ANDROID_SCOPED_TRACE']
    need(len(traces)==1 and type(traces[0]) is dict,'UNCONFIRMED_REAL_PROOF')
    proof=traces[0];dispatch=proof.get('dispatch');audit=proof.get('business_audit')
    need(proof.get('proof_channel')=='REAL_ANDROID_SCOPED_TRACE'
         and proof.get('interaction_id')==t['interaction_id'] and proof.get('status')=='ARRIVAL_VERIFIED'
         and proof.get('actor')==t['actor']=='AGENT_NAVIGATION' and t['status']=='ARRIVAL_VERIFIED',
         'UNCONFIRMED_REAL_PROOF')
    need(type(dispatch) is dict and dispatch.get('dispatched') is True
         and type(dispatch.get('input_api_calls')) is int and dispatch['input_api_calls']==1
         and dispatch.get('business_authorized') is False and dispatch.get('actor')=='AGENT_NAVIGATION',
         'UNCONFIRMED_REAL_PROOF')
    need(type(audit) is dict and type(audit.get('write_count')) is int and audit['write_count']==0
         and type(audit.get('pending_count')) is int and audit['pending_count']==0
         and audit.get('state_unchanged') is True,'UNCONFIRMED_REAL_PROOF')
    ends=[]
    for name,field in [('before','before_observation_id'),('after','after_observation_id')]:
        endpoint=t[name]
        need(endpoint is not None and endpoint['snapshot']==proof.get(field),'UNCONFIRMED_REAL_PROOF')
        observations=[sources[s]['fragment'] for s in t['source_ids']
                      if sources[s]['channel']=='REAL_ANDROID_BOUND_SERVICE'
                      and sources[s]['fragment'].get('observation_id')==endpoint['snapshot']]
        need(len(observations)==1,'UNCONFIRMED_REAL_PROOF');o=observations[0]
        page=next(p for p in pages if p['page_id']==endpoint['page_id'])
        need(any(r['observation_id']==endpoint['snapshot'] for r in page['observation_refs'])
             and o.get('capture_scope_reference')==proof.get('capture_scope_reference'), 'UNCONFIRMED_REAL_PROOF')
        ends.append(o)
    a,b=ends
    need(all(a.get(k)==b.get(k) for k in ('app_package','app_build','process_session'))
         and dispatch.get('observation_id')==a.get('observation_id'),'UNCONFIRMED_REAL_PROOF')
    clocks=[a.get('captured_uptime_ms'),dispatch.get('started_uptime_ms'),
            dispatch.get('finished_uptime_ms'),b.get('captured_uptime_ms')]
    need(all(type(v) is int and v>=0 for v in clocks) and clocks==sorted(clocks),'UNCONFIRMED_REAL_PROOF')
    nodes=[n for n in a.get('tree',{}).get('nodes',[]) if n.get('node_local_id')==dispatch.get('node_local_id')]
    need(len(nodes)==1 and nodes[0].get('resource_id')==dispatch.get('resource_id')
         and all(nodes[0].get(k) is True for k in ('visible','enabled','clickable')),'UNCONFIRMED_REAL_PROOF')


def _validate_page(p,sources):
    expected={'page_id','template_id','label','identity_status','entities','navigation_context','regions','elements',
              'dynamic_state','observation_refs','source_ids','limitations','known_scope'}
    need(type(p) is dict and set(p)==expected,'INVALID_PAGE')
    key(p['page_id'])
    if p['template_id'] is not None:key(p['template_id'])
    need(p['identity_status'] in {'KNOWN','UNKNOWN','AMBIGUOUS','UNAVAILABLE'},'INVALID_PAGE_IDENTITY')
    need(p['label'] is None or type(p['label']) is str,'INVALID_PAGE_LABEL')
    refs(p['source_ids'],sources)
    need(p['source_ids'],'MISSING_PROVENANCE')
    for name,limit in (('entities',128),('regions',256),('elements',2048),('dynamic_state',4096),
                       ('observation_refs',256),('limitations',256)):
        need(type(p[name]) is list and len(p[name])<=limit,'INVALID_PAGE')
    entity_keys=set()
    for e in p['entities']:
        need(type(e) is dict and set(e)=={'entity_key','label','type','basis','source_ids'}
             and e['basis'] in BASIS,'INVALID_ENTITY')
        key(e['entity_key']);need(e['entity_key'] not in entity_keys,'DUPLICATE_ENTITY');entity_keys.add(e['entity_key'])
        refs(e['source_ids'],sources)
        if p['identity_status']=='KNOWN':
            need(e['basis'] in {'OBSERVATION_FACT','RULE_INFERENCE','HUMAN_CONFIRMATION'}
                 and any(sources[s]['basis']=='OBSERVATION_FACT' for s in e['source_ids']),'ENTITY_IDENTITY_NOT_OBSERVATION')
    need(p['identity_status']!='KNOWN' or entity_keys,'EMPTY_KNOWN_IDENTITY')
    region_ids=set()
    for r in p['regions']:
        need(type(r) is dict and set(r)=={'region_id','label','grouping_status','element_refs','source_ids'},'INVALID_REGION')
        key(r['region_id']);need(r['region_id'] not in region_ids,'DUPLICATE_REGION');region_ids.add(r['region_id'])
        refs(r['source_ids'],sources)
    element_ids=set()
    for e in p['elements']:
        need(type(e) is dict and set(e)=={'element_id','entity_key','region_id','role','class_name','resource_id','text',
             'content_description','bounds','visible','enabled','clickable','checkable','range','source_ids','evidence_grade'},
             'INVALID_ELEMENT')
        key(e['element_id']);need(e['element_id'] not in element_ids,'DUPLICATE_ELEMENT');element_ids.add(e['element_id'])
        need(e['entity_key'] is None or e['entity_key'] in entity_keys,'BROKEN_REFERENCE')
        need(e['region_id'] is None or e['region_id'] in region_ids,'BROKEN_REFERENCE')
        need(all(e[k] is None or type(e[k]) is bool for k in ('visible','enabled','clickable','checkable')),'INVALID_ELEMENT')
        need(all(e[k] is None or type(e[k]) is str for k in ('role','class_name','resource_id','text','content_description')),
             'INVALID_ELEMENT')
        need(e['bounds'] is None or type(e['bounds']) is list and len(e['bounds'])==4
             and all(type(v) is int for v in e['bounds']),'INVALID_ELEMENT_BOUNDS')
        need(e['range'] is None or type(e['range']) is dict and set(e['range'])=={'kind','min','max','value'},'INVALID_ELEMENT_RANGE')
        refs(e['source_ids'],sources);need(e['source_ids'],'MISSING_PROVENANCE')
        need(any(sources[s]['basis']=='OBSERVATION_FACT' for s in e['source_ids']),'UI_ELEMENT_NOT_OBSERVATION')
    for r in p['regions']:refs(r['element_refs'],element_ids)
    for o in p['observation_refs']:
        need(type(o) is dict and set(o)=={'observation_id','source_id','capture','status'},'INVALID_OBSERVATION_REFERENCE')
        key(o['observation_id']);need(o['source_id'] in sources,'BROKEN_REFERENCE')
        need(o['status'] in {'HISTORICAL_REFERENCE','OFFLINE_EVIDENCE','LIMITED_CAPTURE_REFERENCE','REAL_ANDROID_REFERENCE'},'INVALID_OBSERVATION_REFERENCE')
        if o['status']=='REAL_ANDROID_REFERENCE':
            need(sources[o['source_id']]['channel']=='REAL_ANDROID_BOUND_SERVICE','PROVENANCE_MISMATCH')


def validate_bundle(value):
    try:
        encoded=canonical(value)
        need(len(encoded.encode('utf-8'))<=MAX_BUNDLE_BYTES,'BUNDLE_SIZE_LIMIT')
        b=sanitize_fragment(value)
        need(canonical(b)==encoded,'UNREDACTED_MATERIAL')
        expected={'kind','schema_version','bundle_id','environment','scope_summary','sources','pages','claims',
                  'interactions','navigation','documents','unknowns','human_participation',
                  'execution_authority','model_upload_authorized','current_ui_confirmed'}
        need(type(b) is dict and set(b)==expected and b['kind']=='LearningBundle' and b['schema_version']=='1.0',
             'INVALID_BUNDLE')
        key(b['bundle_id']); environment(b['environment'])
        need(all(b[k] is False for k in ('execution_authority','model_upload_authorized','current_ui_confirmed')),
             'AUTHORITY_IN_MATERIAL')
        scope=b['scope_summary']
        need(type(scope) is dict and set(scope)=={'learning_mode','known_range','limitations','authorization_status'}
             and scope['authorization_status']=='MATERIAL_ONLY_NO_EXECUTION','INVALID_SCOPE_SUMMARY')
        key(scope['learning_mode'])
        need(type(scope['known_range']) is list and type(scope['limitations']) is list,'INVALID_SCOPE_SUMMARY')
        for name,limit in (('sources',256),('pages',128),('claims',512),('interactions',128),('navigation',128),
                           ('documents',128),('unknowns',256),('human_participation',128)):
            need(type(b[name]) is list and len(b[name])<=limit,'BUNDLE_COLLECTION_LIMIT')
        sources={}
        for s in b['sources']:
            need(type(s) is dict and set(s)=={'source_id','channel','basis','evidence_grade','source_digest',
                 'fragment_digest','fragment_id','fragment','integrity','capture','limitations','untrusted_data','execution_authority'},
                 'INVALID_SOURCE')
            key(s['source_id']); key(s['channel']); key(s['evidence_grade'])
            need(s['source_id'] not in sources and s['basis'] in BASIS,'INVALID_SOURCE')
            need(s['source_digest'] is None or re.fullmatch('[0-9a-f]{64}',s['source_digest']) is not None,'INVALID_DIGEST')
            need(s['fragment_digest']==digest(s['fragment']) and s['fragment_id']==digest({'source':s['source_id'],'fragment':s['fragment']}),
                 'FRAGMENT_DIGEST_ERROR')
            need(s['integrity']=='CONTENT_DIGEST_ONLY_NOT_AUTHENTICATED' and s['untrusted_data'] is True
                 and s['execution_authority'] is False and type(s['limitations']) is list,'INVALID_SOURCE')
            need(s['capture'] is None or type(s['capture']) is dict,'INVALID_CAPTURE_REFERENCE')
            sources[s['source_id']]=s
        page_ids=set()
        for p in b['pages']:
            _validate_page(p,sources)
            need(p['page_id'] not in page_ids,'DUPLICATE_PAGE');page_ids.add(p['page_id'])
        claims=set()
        for c in b['claims']:
            need(type(c) is dict and set(c)=={'claim_id','text','basis','source_ids','page_ids','topic'}
                 and c['basis'] in BASIS and type(c['text']) is str,'INVALID_CLAIM')
            key(c['claim_id']);key(c['topic']);refs(c['source_ids'],sources);refs(c['page_ids'],page_ids)
            need(c['claim_id'] not in claims,'DUPLICATE_CLAIM');claims.add(c['claim_id'])
            need(c['source_ids'] or c['basis']=='UNKNOWN','MISSING_PROVENANCE')
            if c['basis'] not in ('UNKNOWN','RULE_INFERENCE'):
                need(all(sources[s]['basis']==c['basis'] for s in c['source_ids']),'PROVENANCE_MISMATCH')
        steps=set()
        for t in b['interactions']:
            need(type(t) is dict and set(t)=={'interaction_id','actor','actor_assurance','action_label','before','after',
                 'changes','source_ids','status','dispatch_confirmation','limitations'},'INVALID_INTERACTION')
            key(t['interaction_id']);need(t['interaction_id'] not in steps,'DUPLICATE_INTERACTION');steps.add(t['interaction_id'])
            need(t['actor'] in {'HUMAN_DEMONSTRATION','AGENT_NAVIGATION','AGENT_BUSINESS_EXECUTION',
                 'EVALUATOR_INITIALIZATION','UNKNOWN'},'INVALID_ACTOR')
            refs(t['source_ids'],sources)
            for end in (t['before'],t['after']):
                if end is not None:
                    need(type(end) is dict and set(end)=={'page_id','snapshot'} and end['page_id'] in page_ids,'BROKEN_REFERENCE')
            need(t['dispatch_confirmation'] in {'UNCONFIRMED','SIMULATED_ONLY','REAL_NATIVE_RECEIPT'},'UNSUPPORTED_REAL_DISPATCH_CLAIM')
            if t['dispatch_confirmation']=='REAL_NATIVE_RECEIPT':
                _check_inert_real_trace(t,sources,b['pages'])
        for n in b['navigation']:
            need(type(n) is dict and set(n)=={'from_page','to_page','interaction_id','status','source_ids','arrival_verified'},
                 'INVALID_NAVIGATION')
            need(n['from_page'] in page_ids and (n['to_page'] is None or n['to_page'] in page_ids)
                 and (n['interaction_id'] is None or n['interaction_id'] in steps),'BROKEN_REFERENCE')
            need(n['status'] in {'OBSERVED_HISTORICAL_LIMITED','VERIFIED_SIMULATED','OBSERVED_SIMULATED','HYPOTHESIS','INVALIDATED','VERIFIED_REAL_SCOPED'},
                 'UNSUPPORTED_REAL_NAVIGATION_CLAIM');refs(n['source_ids'],sources)
            need(type(n['arrival_verified']) is bool and (not n['arrival_verified'] or n['status'] in {'VERIFIED_SIMULATED','VERIFIED_REAL_SCOPED'}),
                 'FALSE_VERIFIED_NAVIGATION')
            if n['status']=='VERIFIED_REAL_SCOPED':
                step=next(t for t in b['interactions'] if t['interaction_id']==n['interaction_id'])
                need(step['dispatch_confirmation']=='REAL_NATIVE_RECEIPT' and step['before']['page_id']==n['from_page']
                     and step['after']['page_id']==n['to_page'],'FALSE_VERIFIED_NAVIGATION')
        for d in b['documents']:
            need(type(d) is dict and set(d)=={'document_id','source_ids','media_kind','redaction_status','asset_ref'},'INVALID_DOCUMENT')
            key(d['document_id']); refs(d['source_ids'],sources)
            need(d['media_kind'] in {'TEXT','SCREENSHOT_METADATA'} and d['redaction_status']=='REDACTED_METADATA_ONLY',
                 'UNREDACTED_ASSET');key(d['asset_ref'])
        for u in b['unknowns']:
            need(type(u) is dict and set(u)=={'code','status','source_ids'},'INVALID_UNKNOWN')
            key(u['code']);need(u['status'] in {'UNKNOWN','CONFLICT','NOT_TESTED','BLOCKED'},'INVALID_UNKNOWN');refs(u['source_ids'],sources)
        for h in b['human_participation']:
            need(type(h) is dict and set(h)=={'role','status','source_ids','cost_seconds'},'INVALID_HUMAN_RECORD')
            key(h['role']);key(h['status']);refs(h['source_ids'],sources)
            need(h['cost_seconds'] is None or type(h['cost_seconds']) in (int,float) and h['cost_seconds']>=0,'INVALID_COST')
        return b
    except BundleError: raise
    except (TypeError,KeyError,ValueError,RecursionError) as error: raise BundleError('INVALID_BUNDLE') from error
