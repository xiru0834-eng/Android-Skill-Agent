"""Explicit assisted contract review. Original model text and failed checks stay immutable."""
import copy,json,sys,time
from pathlib import Path
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT.parent/'p3-3-layered-validation'))
from p33deps import compiler,environment,contracts,canonical,digest,revision
from layered_validation import format_layer
from learning_request import build_request
from abstraction import occurrences
from bundle_contract import make_source,validate_bundle
from prepare_g1 import save
from lab_transport import adb

def review(out):
    out.mkdir(parents=True,exist_ok=False)
    source=ROOT/'evidence/g2-real-generation-r2/audits/5e7c3d23-1e9b-42fb-be82-616645f3a549'
    origin=json.loads((source/'01-response.json').read_text(encoding='utf-8'))
    draft=json.loads(origin['raw_redacted']);before=copy.deepcopy(draft['candidate_flow'])
    flow=draft['candidate_flow'];edits=[]
    # A preserved property is a declared read dependency, not an extra business CALL.
    for target in flow['must_preserve']:
        cap=contracts.PROPERTIES[target['property']]['name']
        spec=next(i for i in flow['inputs'] if i['name']==target['entity_input'])
        if cap not in spec['required_capabilities']:
            edits.append({'path':'inputs/'+spec['name']+'/required_capabilities','added':cap,
                          'reason':'P1 preserved-property read requires a declared capability dependency'})
            spec['required_capabilities'].append(cap)
        if cap not in flow['dependencies']['capabilities']:flow['dependencies']['capabilities'].append(cap)
    contracts.validate_document(flow)
    if any(before[k]!=flow[k] for k in ('steps','goals','allowed_effects','must_preserve','failure_policy','verification')):
        raise ValueError('BUSINESS_SEMANTICS_CHANGED')
    material=json.loads((ROOT/'evidence/g2-phone-material-r3/learning-bundle.json').read_text(encoding='utf-8'))
    goal=json.loads((source/'input.json').read_text(encoding='utf-8'))['goal']
    public=build_request(goal,[material])
    occ=occurrences(flow,public['allowed_capabilities'])
    capdefs={v['name']:v for v in public['allowed_capabilities']['definitions']}
    calls=[s for s in flow['steps'] if s['op']=='call']
    if len(calls)!=1 or calls[0]['capability']!='SetBrightness':raise ValueError('FLOW_REVIEW_OUTSIDE_AUTHORIZED_GOAL')
    entity_input=calls[0]['entity_input']
    groups=[]
    for spec in flow['inputs']:
        if spec['type']=='entity':continue
        rows=[r for r in occ if r['input_name']==spec['name']]
        if not rows or any(r['property']!='brightnessPercent' or r['entity_input']!=entity_input for r in rows):
            raise ValueError('PARAMETER_REVIEW_UNRESOLVED')
        domain={k:spec[k] for k in ('type','minimum','maximum','step','unit')}
        if domain!={'type':'integer','minimum':0,'maximum':100,'step':1,'unit':'percent'}:raise ValueError('DOMAIN_REVIEW_UNRESOLVED')
        groups.append({'name':spec['name'],'paths':[r['path'] for r in rows],
            'entity_input':entity_input,'property':'brightnessPercent','reason':'Existing public explicit brightness contract',
            'domain':domain,'domain_basis':'APPROVED_ENTITY_CAPABILITY'})
    notes={'schema_version':'1.0','entity_evidence':[{'entity_input':entity_input,'entity_id':'bedroom_light',
        'identity_basis':'PUBLIC_DOCUMENT','supported_capabilities':['SetBrightness','SetPower']}],
        'parameter_groups':groups,'step_roles':[{'step_id':s['id'],
            'role':'REQUIRED_BUSINESS' if s['op']=='call' else 'VERIFICATION' if s['op']=='assert' else 'PROTECTION',
            'reason':'Public contract explicitly requires read/set/check without additional writes'} for s in flow['steps']],
        'explicit_order':[s['id'] for s in flow['steps']],
        'conditions':[{'kind':k,'status':'NOT_REQUIRED','description':'Current public direct absolute setter contract; no extra branch, prerequisite change or Save'}
                      for k in ('BRANCH','PRECONDITION','SUBMISSION')],
        'assistance':{'actor':'HOST_CONTRACT_REVIEW','reason':'Explicit metadata repair and documented parameter/source review; not fully automatic learning',
             'elapsed_seconds':0,'provided_new_rules':True,'provided_new_route':False}}
    for n,s in enumerate(material['sources']):
        if s['source_id']=='public.parameterroom.contract':
            fragment={**s['fragment'],'public_flow_notes':notes}
            material['sources'][n]=make_source(s['source_id'],s['channel'],fragment,basis=s['basis'],grade=s['evidence_grade'],limitations=s['limitations'])
    validate_bundle(material)
    request=build_request(goal,[material])
    revised=revision.propose_parameterization(request,canonical(draft),[material],input_channel='REAL_OPENAI_API')
    save(out/'assisted-source-and-format-review.json',{'model_source':str(source),'model_request_id':origin['request_id'],
        'model_original_sha256':origin['raw_sha256'],'edits':edits,'automatic':False,
        'source_notes_assistance':notes['assistance'],'business_semantics_unchanged':True})
    save(out/'p32-content-review.json',revised)
    if not revised.get('revised_flow'):raise ValueError('CONTENT_REVIEW_NOT_PASSED:'+revised['status'])
    actual=revised['revised_flow'];pkgraw=json.loads(adb('R5CW134LLBZ','shell','run-as','edu.sydney.probe','cat','files/portable-approved.json'))
    profile=environment.audited_room_profile()
    package={'kind':'AppKnowledgePackage','schema_version':'1.0','id':'package.product_brightness','version':'1.0.0',
        'flow_refs':[{'id':actual['id'],'version':actual['version']}],'environment':profile.to_dict()['environment'],
        'entities':[{'entity_id':e['device'],'capabilities':[c['skill'] for c in e['capabilities']]} for e in pkgraw['catalog']],
        'bindings':[],'documentation_refs':['public.parameterroom.contract'],
        'evidence':[{'id':s['source_id'],'kind':'AUDIT_REFERENCE','ref':'material:'+s['source_id'],
                     'description':'Public source; stored evidence only, not execution authority'} for s in material['sources']], 'unknowns':[]}
    task={'kind':'Task','schema_version':'1.0','id':'task.product_validation','flow_ref':package['flow_refs'][0],
        'package_ref':{'id':package['id'],'version':package['version']},'inputs':{entity_input:{'entity_id':'bedroom_light'},groups[0]['name']:60},
        'host_device_id':'host.r5cw134llbz','authorization_ref':'local.explicit_candidate_validation',
        'budget':{'duration_ms':8000,'max_actions':32,'max_model_calls':0},'cancellation_token_ref':'cancel.current_candidate_only'}
    checked,plan=format_layer(actual,package,task,profile)
    save(out/'p33-format-check.json',checked)
    if plan is None:raise ValueError('COMPILE_REJECTED')
    for k,v in [('flow.json',actual),('package.json',package),('task.json',task),('compiled.json',plan.to_dict()),
                 ('review-material.json',material),('review-request.json',request),('assisted-draft.json',draft)]:save(out/k,v)
    return plan
if __name__=='__main__':
    p=review(Path(sys.argv[1]));print(json.dumps({'status':'ASSISTED_STATIC_CHECKED_NOT_YET_DEVICE_VERIFIED','flow_hash':p.to_dict()['flow_hash']}))
