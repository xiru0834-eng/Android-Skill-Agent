"""Versioned current-build capability facts, never portable approval.

The provider is a server-owned callback to the existing read-only lifecycle
worker. HTTP payloads cannot supply it. The worker already verifies exact APK
bytes, Room version and the locally approved catalog. Recheck it after generation
to detect revocation/build changes; execution still needs fresh native resolution
and the ORIGINAL local validation/publication permissions.
"""
import copy,time
from dataclasses import dataclass
from learning_request import build_request as legacy_build,guard,RequestError,MAX_INPUT_BYTES
from p31deps import public_capabilities,canonical,digest

PROBE107_SHA256='9e8135e54f55ba8dc5ceff80c2323a51e69c24bad3962a142c8f745b50e90570'
PROBE108_SHA256='bf3927e8fc3d26ed1a43d36b9657f13fe81dca19764bf2aec4d386bb0e71aef9'
PROBE109_SHA256='353835641160a92c88a65cee6ff2616446bbe61ac4136e8123f4a910579a6377'
PROFILES={PROBE107_SHA256:'parameter-room6.probe107.read-v1',PROBE108_SHA256:'parameter-room6.probe108.read-identity-v1',PROBE109_SHA256:'parameter-room6.probe109.service-audit-v1'}
ENVIRONMENT={'app_package':'edu.sydney.parameterroom','app_build':'6','environment_id':'parameter-room-u0',
             'ui_revision':'ui.u0','domain':'EXPERIMENT_APP'}
MAX_AGE_SECONDS=120
_SEAL=object()

def need(ok,code):
    if not ok:raise RequestError(code)

@dataclass(frozen=True)
class RuntimeSnapshot:
    _public_json:str
    _provider_digest:str
    _captured:float
    _clock:object
    _seal:object
    _identity:object=None
    def public(self):
        need(self._seal is _SEAL,'TRUSTED_RUNTIME_SNAPSHOT_REQUIRED')
        age=self._clock()-self._captured
        need(0<=age<=MAX_AGE_SECONDS,'RUNTIME_PROFILE_EXPIRED')
        import json
        return json.loads(self._public_json)

def capture_snapshot(context,*,clock=time.monotonic,identity_snapshot=None):
    # Called by the trusted service, NOT from parsed model/HTTP request JSON.
    need(type(context) is dict and set(context)=={'environment','probe_apk_sha256','app_version_code',
         'app_version_name','document','execution_authority'},'RUNTIME_CONTEXT_FIELDS')
    guard(context)
    need(context['execution_authority'] is False,'RUNTIME_CONTEXT_AUTHORITY')
    need(context['probe_apk_sha256'] in PROFILES,'CURRENT_PROBE_PROFILE_MISMATCH')
    if identity_snapshot is not None:
        from c2_identity import IdentitySnapshot
        need(type(identity_snapshot) is IdentitySnapshot and context['probe_apk_sha256'] in {PROBE108_SHA256,PROBE109_SHA256},'IDENTITY_BUILD_UNSUPPORTED')
        identity_snapshot.public()
    need(context['environment']==ENVIRONMENT and context['app_version_code']=='6'
         and context['app_version_name']=='0.8-parameter-room','CURRENT_APP_PROFILE_MISMATCH')
    need(type(context['document']) is str and 1<=len(context['document'])<=8000,'RUNTIME_CONTEXT_DOCUMENT')
    capabilities=public_capabilities()
    value={'kind':'CurrentRuntimeCapabilityProfile','schema_version':'1.0',
        'profile_id':PROFILES[context['probe_apk_sha256']],'environment':copy.deepcopy(ENVIRONMENT),
        'probe_apk_sha256':context['probe_apk_sha256'],'app_version_name':'0.8-parameter-room',
        'legacy_capability_digest':digest(capabilities),'native_flow_read_adapter':True,
        'read_contract':'semantic_state_read_v1',
        'provenance':'SERVER_OWNED_EXACT_BUILD_AND_CURRENT_LOCAL_CATALOG_CHECK',
        'identity_assurance':'NOT_ESTABLISHED_BY_PROFILE','execution_authority':False,
        'limitations':['NOT_CURRENT_UI_IDENTITY','NOT_EXECUTION_PERMISSION','NOT_WHOLE_DOMAIN_VERIFICATION']}
    if context['probe_apk_sha256'] in {PROBE108_SHA256,PROBE109_SHA256}:
        # Describes existing exact-build checks, not a grant or a new capability.
        # Capture evidence and future execution admission are different layers.
        value['candidate_validation_contract']={
            'mode':'NORMAL_USER_CANDIDATE_UI',
            'permission':'EXPLICIT_CURRENT_USER_CONFIRMATION_REQUIRED',
            'current_identity':'FRESH_NATIVE_TREE_AND_CANONICAL_RESOLVER_REQUIRED',
            'guards':['CURRENT_PACKAGE_BUILD','ROOT_WINDOW_FOCUS_OVERLAY','UNIQUE_LOCAL_SCOPE',
                      'CURRENT_LOCAL_PACKAGE_APPROVAL','FULL_ENTRY_AND_FINAL_STATE','CANCEL_AND_8000MS_DEADLINE'],
            'on_failed_guard':'REJECT_OR_FAIL_NO_BLIND_INPUT',
            'execution_authority':False}
    return RuntimeSnapshot(canonical(value),digest(context),clock(),clock,_SEAL,identity_snapshot)

def allowed_capabilities(runtime_snapshot):
    need(type(runtime_snapshot) is RuntimeSnapshot,'TRUSTED_RUNTIME_SNAPSHOT_REQUIRED')
    p=runtime_snapshot.public();allowed=public_capabilities()
    need(p['legacy_capability_digest']==digest(allowed),'CAPABILITY_SNAPSHOT_MISMATCH')
    allowed=copy.deepcopy(allowed)
    allowed['native_flow_read_adapter']=True
    allowed['scope']='CURRENT_BUILD_SUPPORTED_SUBSET_NOT_EXECUTION_AUTHORITY'
    allowed['runtime_profile_id']=p['profile_id']
    return allowed

def build_request(goal,bundles,*,store_audit=None,runtime_snapshot=None):
    allowed=allowed_capabilities(runtime_snapshot)
    request=legacy_build(goal,bundles,store_audit=store_audit)
    profile=runtime_snapshot.public()
    need(request['environment']==profile['environment'],'RUNTIME_ENVIRONMENT_MISMATCH')
    request['allowed_capabilities']=allowed
    request['runtime_capability_profile']=profile
    request['schema_version']='1.1-current-runtime'
    request['scope']='STORED_PUBLIC_EVIDENCE_WITH_CURRENT_BUILD_CAPABILITY_FACTS'
    # Only a checked package version relation is resolved. Identity/material
    # gaps, raw model uncertainties and business unknowns are NEVER removed.
    request['knowledge_gaps']=[g for g in request['knowledge_gaps'] if g!='BUILD_VERSION_RELATION_UNCONFIRMED']
    if runtime_snapshot._identity is not None:
        identity=runtime_snapshot._identity.public()
        need(identity['environment']==request['environment'],'IDENTITY_ENVIRONMENT_MISMATCH')
        request['current_identity_evidence']=identity
        known={e['entity_id'] for e in allowed['entity_capabilities']}
        evidenced={l['entity_id'] for a in identity['receipts'] for l in a['links']}
        material_entities={e['entity_key'] for p in request['material']['pages'] if p['identity_status']=='KNOWN' for e in p['entities']}
        need(known<=evidenced and known<=material_entities,'IDENTITY_MATERIAL_INCOMPLETE')
        request['knowledge_gaps']=[g for g in request['knowledge_gaps'] if g!='ENTITY_MAPPING_UNCONFIRMED']
        request['rules'].append('IDENTITY_REFERENCE_ASSISTED_CAPTURE_FACT_NOT_EXECUTION_PERMISSION')
        request['rules'].append('RUNTIME_CHECKS_ARE_EXECUTION_PRECONDITIONS_NOT_CAPTURE_AUTHORITY')
        request['rules'].append('A reusable draft is not a current execution grant. The exact-build candidate validation contract describes required future admission checks. Preserve those requirements; missing business semantics or unsupported checks remain blocking unknowns. Do not treat the absence of a future user confirmation at learning time alone as missing business knowledge, and never assert current execution permission.')
    request.pop('input_digest',None);request.pop('request_id',None)
    need(len(canonical(request).encode())<=MAX_INPUT_BYTES,'INPUT_BYTES_LIMIT')
    request['input_digest']=digest(request)
    import uuid
    request['request_id']=str(uuid.uuid4())
    return request

def validate_request(request,bundles,*,runtime_snapshot=None,original_goal=None):
    need(type(request) is dict and request.get('kind')=='LearningRequest','INPUT_INTEGRITY_ERROR')
    core={k:v for k,v in request.items() if k not in ('input_digest','request_id')}
    need(request.get('input_digest')==digest(core) and request.get('execution_authority') is False
         and request.get('model_upload_authorized') is False,'INPUT_INTEGRITY_ERROR')
    need(len(canonical(request).encode())<=MAX_INPUT_BYTES,'INPUT_SIZE_LIMIT');guard(request)
    # The server retains the original goal only in this call stack. Rebuilding
    # from its sanitized form would change provenance hashes on legitimate
    # redacted input. Never persist or send the original secret to a model.
    rebuilt=build_request(request['goal'] if original_goal is None else original_goal,bundles,
                          store_audit=request.get('store_audit'),runtime_snapshot=runtime_snapshot)
    rebuilt_core={k:v for k,v in rebuilt.items() if k not in ('input_digest','request_id')}
    need(core==rebuilt_core,'MATERIAL_MISMATCH')
    return True

def recheck_provider(runtime_snapshot,context):
    current=capture_snapshot(context)
    runtime_snapshot.public()
    need(current._provider_digest==runtime_snapshot._provider_digest,'CURRENT_RUNTIME_CONTEXT_CHANGED')
    return True
