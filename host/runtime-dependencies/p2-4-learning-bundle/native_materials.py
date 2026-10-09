"""Real native observation/trace adapters, distinct from the frozen offline predecessors.
Tree validation reuses P2.2's pure DTO helper, never its offline channel or simulated permits.
Public marker interpretation is a rule inference, not a hidden entity oracle.
"""
import re
from bundle_contract import need,environment,BundleError,make_source,make_bundle,claim,validate_bundle
from p24deps import canonical,digest
from observation_tree import copy_tree,plain_copy,ObservationError

def copy_native_tree(raw):
    """Validate raw clipped geometry without inventing usable offscreen coordinates."""
    value=plain_copy(raw);unknown=[]
    for n in value.get('nodes',[]):
        b=n.get('bounds')
        if type(b) is list and len(b)==4 and all(type(v) is int for v in b) and (b[2]<b[0] or b[3]<b[1]):
            need(n.get('visible') is False,'VISIBLE_GEOMETRY_INVALID')
            unknown.append(n['node_local_id']);n['bounds']=[0,0,0,0] # internal validator placeholder only
    if unknown:
        value['complete']=False;value['truncated_reasons']=list(value.get('truncated_reasons',[]))+['CLIPPED_GEOMETRY_UNAVAILABLE']
    tree=copy_tree(value)
    for n in tree['nodes']:
        if n['node_local_id'] in unknown:n['bounds']=None # public material never exports placeholder
    tree['geometry_unknown_nodes']=unknown
    return tree

def validate_native_observation(value):
    try:
        o=plain_copy(value)
        need(type(o) is dict and o.get('kind')=='NativePageObservation' and o.get('schema_version')=='1.0','INVALID_NATIVE_OBSERVATION')
        need(o.get('channel')=='REAL_ANDROID_BOUND_SERVICE','WRONG_EVIDENCE_CHANNEL')
        need(type(o.get('observation_id')) is str and re.fullmatch('[0-9a-f]{32}',o['observation_id']) is not None,'INVALID_OBSERVATION_ID')
        need(type(o.get('process_session')) is str and o['process_session'] and re.fullmatch('[0-9a-f]{32}',o.get('scope_id','')) is not None,'INVALID_CAPTURE_SESSION')
        need(o.get('app_package') in {'edu.sydney.transferlab','edu.sydney.parameterroom'} and type(o.get('app_build')) is int and o['app_build']>0,'INVALID_APP_CONTEXT')
        need(o.get('status')=='VALID_TREE_ONLY' and o.get('screenshot') is None and o.get('screenshot_status')=='NOT_REQUESTED'
             and o.get('pairing_level')=='WINDOW_TIME_CHECKED' and o.get('visual_content_check')=='NOT_EVALUATED','INVALID_PAIRING_LEVEL')
        need(type(o.get('window_id')) is int and type(o.get('display_id')) is int,'INVALID_WINDOW')
        for k in ('capture_started_elapsed_ms','captured_elapsed_ms','captured_uptime_ms'):
            need(type(o.get(k)) is int and o[k]>=0,'INVALID_CLOCK')
        need(0<=o['captured_elapsed_ms']-o['capture_started_elapsed_ms']<=2000,'CAPTURE_TIMEOUT')
        need(type(o.get('device_context')) is dict and type(o['device_context'].get('snapshot')) is dict,'DEVICE_CONTEXT_ERROR')
        a=o.get('attempts');need(type(a) is list and 1<=len(a)<=2,'INVALID_ATTEMPTS')
        for index,v in enumerate(a,1):
            need(v['attempt_id']==o['observation_id']+':'+str(index),'INVALID_ATTEMPT_ID')
            if v['status']=='CAPTURE_ATTEMPT_FAILED':
                need(index<len(a) and v.get('error_code') in {'TREE_API_ERROR','ROOT_UNAVAILABLE','WINDOW_MISMATCH','WINDOW_UNAVAILABLE'}
                     and type(v.get('started_elapsed_ms')) is int and type(v.get('finished_elapsed_ms')) is int
                     and o['capture_started_elapsed_ms']<=v['started_elapsed_ms']<=v['finished_elapsed_ms']<=o['captured_elapsed_ms'],'INVALID_FAILED_ATTEMPT')
                continue
            times=[v[k] for k in ('tree_a_start_uptime_ms','tree_a_end_uptime_ms','tree_b_start_uptime_ms','tree_b_end_uptime_ms')]
            need(all(type(t) is int and t>=0 for t in times) and times==sorted(times),'INVALID_CLOCK')
            need(index==len(a) or v['status']=='OBSERVATION_INCONSISTENT','INVALID_ATTEMPTS')
        last=a[-1];need(last['status']=='VALID_TREE_ONLY','OBSERVATION_INCONSISTENT')
        need(last['tree_b_end_uptime_ms']-last['tree_a_start_uptime_ms']<=250,'PAIRING_SPAN_EXCEEDED')
        need(last['tree_b_end_uptime_ms']==o['captured_uptime_ms'],'INVALID_CAPTURE_TIME')
        for snap in (last['tree_a'],last['tree_b']):
            need(snap['window_id']==o['window_id'] and snap['display_id']==o['display_id'],'WINDOW_MISMATCH');copy_native_tree(snap['tree'])
        need(canonical(last['tree_a']['tree'])==canonical(last['tree_b']['tree'])==canonical(o['tree']),'OBSERVATION_INCONSISTENT')
        tree=copy_native_tree(o['tree'])
        need(all(n['package']==o['app_package'] for n in tree['nodes']),'EXTERNAL_NODE_IN_TREE')
        return o
    except BundleError:raise
    except (ObservationError,TypeError,ValueError,KeyError,RecursionError) as e:raise BundleError('INVALID_NATIVE_OBSERVATION') from e

def _public_context(o):
    nodes=o['tree']['nodes'];markers=[n for n in nodes if n['visible'] and n['resource_id']==o['app_package']+':id/wfPage']
    if len(markers)>1:return 'AMBIGUOUS',None,None
    if len(markers)!=1 or type(markers[0]['text']) is not str:return 'UNKNOWN',None,None
    m=re.fullmatch(r'(overview|lamp|fan|single)\s*\|\s*(\S.{0,100})',markers[0]['text'])
    if not m:return 'UNKNOWN',None,None
    return 'KNOWN',m[1],m[2].strip()

def _public_label_terms(text):
    # Whole bilingual label segments, not arbitrary substring/prompt content.
    return {term.strip().casefold() for term in re.split(r'\s*/\s*',text) if term.strip()} if type(text) is str else set()

def derive_native_page(observation,env,source_id):
    o=validate_native_observation(observation);env=environment(env)
    need(env['app_package']==o['app_package'] and env['app_build']==str(o['app_build']),'ENVIRONMENT_VERSION_MISMATCH')
    tree=copy_native_tree(o['tree']);nodes=tree['nodes'];index={n['node_local_id']:n for n in nodes}
    status,hint,room=_public_context(o)
    host=o['device_context']['snapshot'].get('deviceId') or o['device_context']['snapshot'].get('hostDeviceId') or 'UNKNOWN_HOST.'+o['process_session']
    # Shape excludes values/bounds; public identity digits are never stripped.
    shape=[{'parent':n['parent_local_id'],'role':n['role'],'class':n['class_name'],'resource_id':n['resource_id'],
            'range_kind':n['range']['kind'] if n['range'] else None} for n in nodes]
    template=digest({'shape':shape});nav={'page_hint':hint,'entity_context':room,'tab':None,'popup':None,'expanded':None,
        'visible_slice':digest([(n['node_local_id'],n['visible'],n['bounds']) for n in nodes])}
    basis={'env':env,'host':host,'template':template,'page_hint':hint,'room':room}
    if status!='KNOWN':basis['unknown_observation']=o['observation_id']
    pid=digest(basis);entities=[];anchors={}
    # Both explicit room context and the displayed object label are required for ownership.
    if status=='KNOWN':
        expected_labels=['Reading lamp','Desk fan'] if hint=='single' else [{'lamp':'Reading lamp','fan':'Desk fan'}[hint]] if hint in {'lamp','fan'} else []
        if expected_labels:
            for label in expected_labels:
                labels=[n for n in nodes if n['visible'] and label.casefold() in _public_label_terms(n['text'])]
                if len(labels)!=1:status='AMBIGUOUS' if len(labels)>1 else 'UNKNOWN';break
                anchor=labels[0]['parent_local_id'];entity_key=digest({'room':room,'public_object':label})
                entities.append({'entity_key':entity_key,'label':room+' / '+label,'type':'PUBLIC_UI_OBJECT',
                                 'basis':'RULE_INFERENCE','source_ids':[source_id]})
                # Same ancestor with multiple objects is explicitly UNASSIGNED, not assigned to the last.
                if anchor in anchors:anchors[anchor]=None
                else:anchors[anchor]=entity_key
        else:
            entity_key=digest({'public_room':room});entities.append({'entity_key':entity_key,'label':room,'type':'ROOM',
                'basis':'RULE_INFERENCE','source_ids':[source_id]});anchors[tree['root_local_id']]=entity_key
    if status!='KNOWN':
        entities=[];anchors={};pid=digest({**basis,'unknown_observation':o['observation_id']})
    if not anchors:anchors={tree['root_local_id']:None}
    regions={a:{'region_id':digest({'page':pid,'anchor':a}),'label':next((e['label'] for e in entities if e['entity_key']==owner),None),
                'grouping_status':'PUBLIC_ANCESTOR_RULE_INFERENCE' if owner else 'UNASSIGNED_MULTI_OWNER','element_refs':[],'source_ids':[source_id]} for a,owner in anchors.items()}
    elements=[];dynamic=[]
    for n in nodes:
        cursor=n['node_local_id'];anchor=None
        while cursor is not None:
            if cursor in anchors:anchor=cursor;break
            cursor=index[cursor]['parent_local_id']
        region=regions[anchor]['region_id'] if anchor in regions else None
        eid=digest({'observation':o['observation_id'],'node':n['node_local_id']})
        e={'element_id':eid,'entity_key':anchors.get(anchor),'region_id':region,
           **{k:n[k] for k in ('role','class_name','resource_id','text','content_description','bounds','visible','enabled','clickable','checkable','range')},
           'source_ids':[source_id],'evidence_grade':'REAL_PUBLIC_TREE_FACT'}
        elements.append(e)
        if anchor in regions:regions[anchor]['element_refs'].append(eid)
        if n['visible'] and (n['checkable'] or n['range'] or n['selected']):
            dynamic.append({'element_id':eid,'checked':n['checked'] if n['checkable'] else None,'selected':n['selected'],
                            'value':n['range']['value'] if n['range'] else None,'source_id':source_id})
    return {'page_id':pid,'template_id':template,'label':(' | '.join([hint,room]) if hint and room else None),'identity_status':status,
            'entities':entities,'navigation_context':nav,'regions':list(regions.values()),'elements':elements,'dynamic_state':dynamic,
            'observation_refs':[{'observation_id':o['observation_id'],'source_id':source_id,'capture':{'elapsed_ms':o['captured_elapsed_ms'],
                'process_session':o['process_session'],'window_id':o['window_id']},'status':'REAL_ANDROID_REFERENCE'}],
            'source_ids':[source_id],'limitations':['STORED_NOT_LIVE','TREE_ONLY_NO_VISUAL_CHECK','PUBLIC_MARKER_RULE_NOT_GENERAL_APP_IDENTITY']+(['CLIPPED_GEOMETRY_UNAVAILABLE'] if tree['geometry_unknown_nodes'] else []),
            'known_scope':tree['known_scope']}

def validate_native_interaction(value):
    try:
        t=plain_copy(value)
        need(type(t) is dict and set(t)=={'interaction_id','actor','before','dispatch','after','events','business_audit','status'},'INVALID_REAL_INTERACTION')
        need(t['actor']=='AGENT_NAVIGATION' and t['status']=='ARRIVAL_VERIFIED','INVALID_REAL_ACTOR')
        a=validate_native_observation(t['before']);b=validate_native_observation(t['after']);d=t['dispatch']
        need(a['scope_id']==b['scope_id']==d['scope_id'] and a['process_session']==b['process_session'] and a['app_package']==b['app_package']
             and a['app_build']==b['app_build'],'TRACE_CONTEXT_CONFLICT')
        need(d['observation_id']==a['observation_id'] and d['input_api_calls']==1 and d['dispatched'] is True and d['actor']=='AGENT_NAVIGATION'
             and d['business_authorized'] is False and d['actor_assurance']=='DUMP_PROTECTED_DETERMINISTIC_CONTROLLER','UNCONFIRMED_DISPATCH')
        need(a['captured_uptime_ms']<=d['started_uptime_ms']<=d['finished_uptime_ms']<=b['captured_uptime_ms'],'TRACE_CLOCK_ERROR')
        nodes=[n for n in a['tree']['nodes'] if n['node_local_id']==d['node_local_id']]
        need(len(nodes)==1 and nodes[0]['resource_id']==d['resource_id'] and nodes[0]['visible'] and nodes[0]['enabled'] and nodes[0]['clickable'],'INVALID_DISPATCH_NODE')
        need(type(t['business_audit']) is dict and t['business_audit'].get('write_count')==0 and t['business_audit'].get('pending_count')==0
             and t['business_audit'].get('state_unchanged') is True,'UNSAFE_NAVIGATION_WRITES')
        need(_public_context(a)[0]==_public_context(b)[0]=='KNOWN' and _public_context(a)[1:]!=_public_context(b)[1:],'ARRIVAL_UNCONFIRMED')
        need(type(t['events']) is list and all(type(e) is dict and e.get('source')=='ANDROID_ACCESSIBILITY_EVENT' and e.get('actor')=='UNKNOWN' for e in t['events']),'INVALID_EVENT_RECORD')
        return t
    except BundleError:raise
    except (ObservationError,TypeError,KeyError,ValueError) as e:raise BundleError('INVALID_REAL_INTERACTION') from e

def _inert_observation(o):
    out={k:v for k,v in o.items() if k!='scope_id'}
    out['capture_scope_reference']=digest(o['scope_id']);return out

def _inert_trace(t):
    return {'interaction_id':t['interaction_id'],'actor':t['actor'],'before_observation_id':t['before']['observation_id'],
        'after_observation_id':t['after']['observation_id'],'dispatch':{k:v for k,v in t['dispatch'].items() if k!='scope_id'},
        'capture_scope_reference':digest(t['before']['scope_id']),'events':t['events'],'business_audit':t['business_audit'],
        'status':'ARRIVAL_VERIFIED','proof_channel':'REAL_ANDROID_SCOPED_TRACE'}

def native_bundle(observations,interactions,env):
    env=environment(env);b=make_bundle(env,mode='SCOPED_ANDROID_LEARNING');pages={};obsmap={}
    for raw in observations:
        o=validate_native_observation(raw);sid='native.'+o['observation_id']
        need(o['observation_id'] not in obsmap,'DUPLICATE_OBSERVATION')
        b['sources'].append(make_source(sid,o['channel'],_inert_observation(o),basis='OBSERVATION_FACT',grade='REAL_BOUND_SERVICE_TREE',
            source_digest=digest(o),capture={'elapsed_ms':o['captured_elapsed_ms'],'process_session':o['process_session'],'window_id':o['window_id']},
            limitations=['NOT_ATOMIC_FRAME','NO_VISUAL_CONTENT_CHECK','DIGEST_NOT_SOURCE_AUTHENTICATION']))
        p=derive_native_page(o,env,sid);pid=p['page_id'];old=pages.get(pid)
        if old:p['source_ids']=old['source_ids']+p['source_ids'];p['observation_refs']=old['observation_refs']+p['observation_refs']
        pages[pid]=p;obsmap[o['observation_id']]=(pid,sid)
    b['pages']=list(pages.values())
    for raw in interactions:
        t=validate_native_interaction(raw);a,bref=t['before']['observation_id'],t['after']['observation_id']
        need(a in obsmap and bref in obsmap,'BROKEN_REFERENCE');sid='trace.'+t['interaction_id'];fragment=_inert_trace(t)
        b['sources'].append(make_source(sid,'REAL_ANDROID_SCOPED_TRACE',fragment,basis='OBSERVATION_FACT',grade='REAL_NAVIGATION_EVIDENCE',source_digest=digest(t),
            limitations=['ACTOR_ATTRIBUTED_BY_PROTECTED_CONTROLLER_NOT_PASSIVE_EVENT','NO_BUSINESS_EXECUTION_TESTED']))
        p1,s1=obsmap[a];p2,s2=obsmap[bref]
        b['interactions'].append({'interaction_id':t['interaction_id'],'actor':t['actor'],'actor_assurance':'PROTECTED_CONTROLLER_DISPATCH',
            'action_label':t['dispatch']['resource_id'],'before':{'page_id':p1,'snapshot':a},'after':{'page_id':p2,'snapshot':bref},
            'changes':{'navigation':True,'business':'NO_WRITES_OBSERVED'},'source_ids':[sid,s1,s2],'status':'ARRIVAL_VERIFIED',
            'dispatch_confirmation':'REAL_NATIVE_RECEIPT','limitations':['NO_BUSINESS_AUTHORITY','BOUNDED_CONTROLLED_APP_EVIDENCE']})
        b['navigation'].append({'from_page':p1,'to_page':p2,'interaction_id':t['interaction_id'],'status':'VERIFIED_REAL_SCOPED',
            'source_ids':[sid,s1,s2],'arrival_verified':True})
    for p in b['pages']:
        b['claims'].append(claim('Public page evidence: '+(p['label'] or p['identity_status']),'RULE_INFERENCE',p['source_ids'],page_ids=[p['page_id']],topic='PAGE_IDENTITY'))
    b['scope_summary']['known_range']=[{'page_id':p['page_id'],'status':p['identity_status'],'scope':p['known_scope']} for p in b['pages']]
    b['scope_summary']['limitations']=['ONLY_OBSERVED_EXPERIMENT_APP_PAGES','NO_ARBITRARY_APP_DIRECTORY','MODEL_CALLS_0','NO_SCREENSHOT_CONTENT_CHECK']
    b['unknowns']=[{'code':'UNOBSERVED_APP_CONTENT','status':'UNKNOWN','source_ids':[]},
                   {'code':'VISUAL_MODEL_EXPERIMENT','status':'NOT_TESTED','source_ids':[]}]
    b['human_participation']=[{'role':'APP_HANDLER_AUDIT','status':'MANUAL_POLICY_PREPARATION','source_ids':[], 'cost_seconds':None}]
    return validate_bundle(b)
