"""Thin P2 adapter and versioned read-dependency normalization; never Android input."""
import copy,sys
from pathlib import Path
BASE=Path(__file__).resolve().parent/'runtime-dependencies'
sys.path.insert(0,str(BASE/'p3-1-draft-generator'))
from p31deps import contracts,canonical,digest,bundle_contract
sys.path.insert(0,str(BASE/'p2-4-learning-bundle'))
from native_materials import native_bundle

def append_current_context(bundle,context):
    """Deployment-owned public facts only. Old capability snapshot stays untouched.
    HTTP callers cannot set this context; it never supplies locators or state answers.
    """
    keys={'environment','probe_apk_sha256','app_version_code','app_version_name','document','execution_authority'}
    if type(context) is not dict or set(context)!=keys or context['execution_authority'] is not False:
        raise ValueError('CURRENT_CONTEXT_CONTRACT')
    if context['environment']!=bundle['environment'] or type(context['document']) is not str or not 0<len(context['document'])<=8000:
        raise ValueError('CURRENT_CONTEXT_ENVIRONMENT')
    if context['app_version_code']!=bundle['environment']['app_build']:
        raise ValueError('CURRENT_CONTEXT_BUILD')
    import re
    if not re.fullmatch('[a-f0-9]{64}',context['probe_apk_sha256']):raise ValueError('CURRENT_CONTEXT_DIGEST')
    result=copy.deepcopy(bundle)
    # P3's public projector intentionally reads only a text field, never raw paths or private approval.
    result['sources'].append(bundle_contract.make_source('public.current.runtime','CURRENT_DEPLOYMENT_PUBLIC_CONTRACT',
        {'text':context['document'],'metadata_digest':digest(context)},basis='DOCUMENTATION_STATEMENT',
        grade='EXACT_INSTALLED_BUILD_AND_LOCAL_APPROVED_CATALOG_CHECK',
        limitations=['NOT_CURRENT_UI_IDENTITY','NOT_EXECUTION_AUTHORITY','NOT_WHOLE_DOMAIN_VERIFICATION']))
    return bundle_contract.validate_bundle(result)

def from_recording(observations,legacy_trace,document,environment,events=None,*,identity_snapshot=None):
    if type(observations) is not list or len(observations)>64 or type(document) is not str or len(document)>16000:
        raise ValueError('MATERIAL_CONTRACT')
    if not observations and legacy_trace is None and not document.strip():raise ValueError('MATERIAL_EMPTY')
    if observations:
        bundle=native_bundle(observations,[],environment)
        from c2_identity import derive_page
        pages={}
        for o in observations:
            sid='native.'+o['observation_id'];p=derive_page(o,environment,sid,identity_snapshot)
            old=pages.get(p['page_id'])
            if old:p['source_ids']=old['source_ids']+p['source_ids'];p['observation_refs']=old['observation_refs']+p['observation_refs']
            pages[p['page_id']]=p
        bundle['pages']=list(pages.values())
        bundle['scope_summary']['known_range']=[{'page_id':p['page_id'],'status':p['identity_status'],'scope':p['known_scope']} for p in bundle['pages']]
        # Replace only this new bundle's derived page summary, never old evidence.
        bundle['claims']=[bundle_contract.claim('Public page evidence: '+(p['label'] or p['identity_status']),'RULE_INFERENCE',p['source_ids'],page_ids=[p['page_id']],topic='PAGE_IDENTITY') for p in bundle['pages']]
    else:
        bundle=bundle_contract.make_bundle(environment,mode='DOCUMENT_ASSISTED' if legacy_trace is None else 'DEMONSTRATION_ASSISTED')
    mode='DEMONSTRATION_ASSISTED' if observations or legacy_trace is not None else 'DOCUMENT_ASSISTED'
    bundle['scope_summary']['learning_mode']=mode
    limitations=bundle['scope_summary']['limitations']
    if legacy_trace is not None:
        if (type(legacy_trace) is not dict or legacy_trace.get('end') not in {'STOPPED','COMPLETED'} or legacy_trace.get('error')
            or type(legacy_trace.get('steps')) is not list or not 1<=len(legacy_trace['steps'])<=128
            or any(type(s) is not dict for s in legacy_trace['steps'])):
            raise ValueError('RECORDING_INCOMPLETE')
        if 'appPackage' in legacy_trace and legacy_trace['appPackage']!=environment['app_package']:raise ValueError('RECORDING_ENVIRONMENT_MISMATCH')
        if 'appVersion' in legacy_trace and legacy_trace['appVersion']!=environment['app_build']:raise ValueError('RECORDING_ENVIRONMENT_MISMATCH')
        # Legacy snapshots remain source fragments. They do not become native pages or verified edges.
        bundle['sources'].append(bundle_contract.make_source('legacy.recording','LEGACY_WORKFLOW_TRACE',legacy_trace,
            basis='OBSERVATION_FACT',grade='RECORDER_CLAIM_NOT_INDEPENDENT_PROOF',limitations=['LEGACY_TRACE_NOT_PAGE_MEMORY','ACTOR_DECLARATION_ONLY']))
        limitations.append('LEGACY_TRACE_NOT_PAGE_MEMORY')
        for n,step in enumerate(legacy_trace['steps']):
            public={k:step[k] for k in ('id','before','after') if k in step}
            bundle['claims'].append(bundle_contract.claim('Legacy recorder claim '+str(n+1)+': '+canonical(public),
                'UNKNOWN',['legacy.recording'],topic='UNVERIFIED_RECORDED_TRANSITION'))
        bundle['human_participation'].append({'role':'DEMONSTRATOR','status':'HUMAN_DECLARED_NOT_INDEPENDENTLY_ATTRIBUTED',
            'source_ids':['legacy.recording'],'cost_seconds':None})
    if events is not None:
        if type(events) is not dict or type(events.get('events')) is not list or len(events['events'])>256:raise ValueError('EVENT_CONTRACT')
        if any(type(e) is not dict or e.get('source')!='ANDROID_ACCESSIBILITY_EVENT' or e.get('actor')!='UNKNOWN' for e in events['events']):raise ValueError('EVENT_ACTOR_UNPROVEN')
        bundle['sources'].append(bundle_contract.make_source('passive.events','ANDROID_ACCESSIBILITY_EVENTS',events,
            basis='OBSERVATION_FACT',grade='PASSIVE_EVENTS_NOT_DISPATCH_PROOF',limitations=['ACTOR_UNKNOWN','NO_VERIFIED_ACTION_EDGE']))
    if document.strip():
        ids=[]
        for n in range(0,len(document),4000):
            sid='user.document' if len(document)<=4000 else 'user.document.'+str(n//4000);ids.append(sid)
            bundle['sources'].append(bundle_contract.make_source(sid,'USER_PROVIDED_DOCUMENT',{'text':document[n:n+4000]},
                basis='DOCUMENTATION_STATEMENT',grade='USER_DOCUMENT_UNCONFIRMED',limitations=['NOT_CURRENT_UI_IDENTITY','UNTRUSTED_DATA']))
        bundle['human_participation'].append({'role':'DOCUMENT_PROVIDER','status':'DOCUMENT_ASSISTED','source_ids':ids,'cost_seconds':None})
    bundle['unknowns'].append({'code':'MATERIAL_NOT_CURRENT_EXECUTION_OR_IDENTITY_AUTHORITY','status':'UNKNOWN','source_ids':[]})
    bundle['scope_summary']['limitations']+=['NO_IMPLICIT_DEVICE_ACTION','NO_AUTOMATIC_PUBLICATION']
    return bundle_contract.validate_bundle(bundle)

def normalize_read_dependencies(flow,*,allowed=None):
    """Complete only preservation reads derivable from the frozen property registry."""
    # A missing declared read is rejected by P1 itself. Preserve that failure,
    # allow only this reference error into the bounded normalizer, then fully recheck.
    contracts.parse_document(canonical(flow))
    try:contracts.validate_document(flow)
    except contracts.ContractError as error:
        if error.code!='BAD_REFERENCE':raise
    if flow.get('kind')!='FlowSkill' or flow.get('verified_scope')!=[]:raise ValueError('DRAFT_ONLY')
    result=copy.deepcopy(flow);diff=[]
    allowed=set(contracts.CAPS) if allowed is None else set(allowed)
    for target in result['must_preserve']:
        prop=target['property'];definition=contracts.PROPERTIES.get(prop)
        if definition is None or definition['name'] not in allowed:raise ValueError('READ_CAPABILITY_UNSUPPORTED')
        cap=definition['name'];name=target['entity_input']
        spec=next((i for i in result['inputs'] if i['name']==name and i['type']=='entity'),None)
        if spec is None:raise ValueError('READ_ENTITY_UNRESOLVED')
        for container,path in ((spec['required_capabilities'],f'/inputs/{result["inputs"].index(spec)}/required_capabilities'),
                              (result['dependencies']['capabilities'],'/dependencies/capabilities')):
            if cap not in container:
                before=list(container);container.append(cap)
                diff.append({'path':path,'before':before,'after':list(container),'reason':'DECLARED_PRESERVATION_READ',
                             'property':prop,'source':'PINNED_PROPERTY_CAPABILITY_REGISTRY'})
    contracts.validate_document(result)
    return {'flow':result,'original_hash':digest(flow),'normalized_hash':digest(result),'diff':diff,
            'normalizer_version':'preservation-reads-v1','mode':'PROGRAM_NORMALIZATION','execution_authority':False}
