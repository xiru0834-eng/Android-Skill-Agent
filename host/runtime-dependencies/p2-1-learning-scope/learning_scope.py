"""Learning definition and gap assessment only; no UI/model/Skill operations."""
from dataclasses import dataclass
import json
import re
import time

from p21deps import contracts, digest

ScopeError = contracts.ContractError
need = contracts.need
MODES = ('AUTO_UI', 'DEMONSTRATION_ASSISTED', 'DOCUMENT_ASSISTED', 'EXPERT_CORRECTED')
DOMAINS = ('EXPERIMENT_APP', 'TEACHER_APP')
CHANNELS = ('TEST_FIXTURE', 'HISTORICAL_ANDROID_TRACE', 'DOCUMENT', 'EXPERT_NOTE', 'CURRENT_UI')
MODE_CHANNELS = {'AUTO_UI': {'CURRENT_UI', 'TEST_FIXTURE'},
                 'DEMONSTRATION_ASSISTED': {'HISTORICAL_ANDROID_TRACE', 'TEST_FIXTURE'},
                 'DOCUMENT_ASSISTED': {'DOCUMENT', 'TEST_FIXTURE'},
                 'EXPERT_CORRECTED': {'EXPERT_NOTE', 'TEST_FIXTURE'}}
ID = {'type': 'string', 'min_length': 1, 'max_length': 120, 'pattern': '[A-Za-z0-9_.:-]+'}
TEXT = {'type': 'string', 'min_length': 1, 'max_length': 2000}
HASH = {'type': 'string', 'pattern': '[a-f0-9]{64}'}
BOOLEAN = {'type': 'boolean'}
NULL = {'const': None}


def array(item, maximum=128, minimum=0):
    return {'list': item, 'min': minimum, 'max': maximum, 'unique': True}


def enum(*values):
    return {'type': 'string', 'enum': list(values)}


def nullable(rule):
    return {'union': [NULL, rule]}


def integer(maximum, minimum=0):
    return {'type': 'integer', 'min': minimum, 'max': maximum}


SCHEMA = {'record': {
    'kind': {'const': 'LearningScope'}, 'schema_version': {'const': '1.0'}, 'scope_id': ID,
    'target': {'record': {
        'app_package': ID, 'app_build': nullable(TEXT), 'environment_id': ID,
        'ui_revision': nullable(ID), 'domain': enum(*DOMAINS),
    }},
    'task': {'record': {
        'goal': nullable(TEXT), 'entity_types': array(ID),
        'known_start_page': nullable(ID), 'origin_source_ids': array(ID),
    }},
    'allowed_pages': array(ID), 'modes': array(enum(*MODES), 4, 1),
    'sources': array({'record': {
        'source_id': ID, 'mode': enum(*MODES),
        'actor': enum('HUMAN_DECLARED', 'AUTOMATED', 'DOCUMENT_AUTHOR', 'EXPERT', 'UNKNOWN'),
        'channel': enum(*CHANNELS), 'evidence_ref': TEXT, 'sha256': HASH,
        'origin': {'record': {'domain': enum(*DOMAINS), 'app_package': nullable(ID),
                              'app_build': nullable(TEXT)}},
    }}),
    'requested_permissions': {'record': {
        'observe': BOOLEAN, 'navigation': array(ID),
        'business_writes': array({'record': {'entity_id': ID, 'property': ID}}),
    }},
    'authorization_refs': array(ID),
    'budgets': {'record': {
        'max_time_ms': integer(3600000, 1), 'max_observations': integer(100000),
        'max_actions': integer(100000), 'max_model_requests': integer(10000),
        'max_storage_bytes': integer(67108864),
    }},
}}


def bounded_document(value):
    if type(value) in (str, bytes):
        result = contracts.parse_document(value)
    else:
        contracts._budget(value)  # Fixed P1.2 internal primitive; unchanged.
        result = contracts.parse_document(json.dumps(value, ensure_ascii=False, allow_nan=False))
    # Known credential forms: avoid persisting obvious keys; not a general PII detector.
    need(not re.search(r'sk-(?:proj-|ws-|[A-Za-z0-9_-]{20})', json.dumps(result)), 'SENSITIVE_INPUT')
    return result


def validate_scope(value):
    scope = bounded_document(value)
    contracts._shape(scope, SCHEMA)
    sources = scope['sources']
    ids = [item['source_id'] for item in sources]
    need(len(ids) == len(set(ids)), 'DUPLICATE_ID')
    need(set(scope['task']['origin_source_ids']) <= set(ids), 'BAD_REFERENCE')
    need({item['mode'] for item in sources} <= set(scope['modes']), 'SOURCE_MODE_MISMATCH')
    for source in sources:
        need(source['channel'] in MODE_CHANNELS[source['mode']], 'SOURCE_CHANNEL_MISMATCH')
        if source['mode'] == 'AUTO_UI':
            need(source['actor'] in ('AUTOMATED', 'UNKNOWN'), 'SOURCE_ACTOR_MISMATCH')
    start = scope['task']['known_start_page']
    need(start is None or start in scope['allowed_pages'], 'START_OUTSIDE_SCOPE')
    # Identifiers do not accept wildcards. No implicit whole-App interpretation.
    return scope


def scope_digest(scope):
    return digest(validate_scope(scope))


@dataclass(frozen=True)
class MaterialReceipt:
    source_id: str
    sha256: str
    domain: str


@dataclass(frozen=True)
class ScopeAuthorization:
    """Local simulation input, NOT an Android approval issuer or portable permit."""
    scope_hash: str
    environment_id: str
    host_device_id: str
    deadline_ms: int
    observe: bool = False
    navigation: tuple = ()
    business_writes: tuple = ()
    model_requests: int = 0
    source: str = 'TEST_FIXTURE_NOT_NATIVE_APPROVAL'


@dataclass(frozen=True)
class ReadinessContext:
    app_available: bool = False
    app_build: str | None = None
    environment_id: str | None = None
    ui_revision: str | None = None
    materials: tuple = ()
    authorization: ScopeAuthorization | None = None
    formal_gate_pass: bool = False


def assess_scope(value, context=None, *, now_ms=None):
    scope = validate_scope(value)
    context = context if context is not None else ReadinessContext()
    need(type(context) is ReadinessContext, 'UNTRUSTED_CONTEXT')
    need(type(context.app_available) is bool and type(context.formal_gate_pass) is bool, 'TYPE_MISMATCH')
    now = int(time.monotonic() * 1000) if now_ms is None else now_ms
    need(type(now) is int and now >= 0, 'INVALID_CLOCK')
    target, task = scope['target'], scope['task']
    gaps = []
    if not task['goal'] or not task['entity_types'] or not task['known_start_page'] or not scope['allowed_pages']:
        gaps.append('GAP_TASK_UNCLEAR')
    if not task['origin_source_ids']:
        gaps.append('GAP_TASK_ORIGIN_MISSING')
    if target['app_build'] is None or target['ui_revision'] is None:
        gaps.append('GAP_BUILD_UNKNOWN')
    if not context.app_available:
        gaps.append('GAP_APP_UNAVAILABLE')
    elif (context.app_build, context.environment_id, context.ui_revision) != (
            target['app_build'], target['environment_id'], target['ui_revision']):
        gaps.append('GAP_ENVIRONMENT_MISMATCH')
    receipts = {}
    need(type(context.materials) is tuple and len(context.materials) <= 128, 'UNTRUSTED_CONTEXT')
    for receipt in context.materials:
        need(type(receipt) is MaterialReceipt, 'UNTRUSTED_CONTEXT')
        contracts._shape(receipt.source_id, ID)
        contracts._shape(receipt.sha256, HASH)
        need(receipt.domain in DOMAINS, 'UNTRUSTED_CONTEXT')
        need(receipt.source_id not in receipts, 'DUPLICATE_ID')
        receipts[receipt.source_id] = receipt
    if not scope['sources'] or any(
            item['source_id'] not in receipts or receipts[item['source_id']].sha256 != item['sha256']
            or receipts[item['source_id']].domain != target['domain'] for item in scope['sources']):
        gaps.append('GAP_MATERIAL_UNAVAILABLE')
    if {item['mode'] for item in scope['sources']} != set(scope['modes']):
        gaps.append('GAP_MODE_EVIDENCE')
    if any(item['origin']['domain'] != target['domain'] for item in scope['sources']):
        gaps.append('GAP_SOURCE_DOMAIN_MISMATCH')
    if any(item['origin']['app_package'] != target['app_package']
           and item['mode'] != 'DOCUMENT_ASSISTED' for item in scope['sources']):
        gaps.append('GAP_SOURCE_APP_MISMATCH')
    if any(item['channel'] == 'CURRENT_UI' and item['origin']['app_build'] != target['app_build']
           for item in scope['sources']):
        gaps.append('GAP_CURRENT_UI_BUILD_MISMATCH')
    authorization = context.authorization
    auth_ok = type(authorization) is ScopeAuthorization
    if auth_ok:
        auth_ok = (authorization.source == 'TEST_FIXTURE_NOT_NATIVE_APPROVAL'
                   and type(authorization.deadline_ms) is int and now < authorization.deadline_ms
                   and authorization.scope_hash == digest(scope)
                   and authorization.environment_id == target['environment_id']
                   and type(authorization.host_device_id) is str and bool(authorization.host_device_id)
                   and type(authorization.observe) is bool)
    if not auth_ok:
        gaps.append('GAP_CURRENT_AUTHORIZATION')
    else:
        permission = scope['requested_permissions']
        requested_writes = {(w['entity_id'], w['property']) for w in permission['business_writes']}
        need(type(authorization.navigation) is tuple and type(authorization.business_writes) is tuple,
             'UNTRUSTED_CONTEXT')
        need(len(authorization.navigation) <= 128 and len(authorization.business_writes) <= 128,
             'UNTRUSTED_CONTEXT')
        for action in authorization.navigation:
            contracts._shape(action, ID)
        for write in authorization.business_writes:
            need(type(write) is tuple and len(write) == 2, 'UNTRUSTED_CONTEXT')
            for value in write:
                contracts._shape(value, ID)
        if (permission['observe'] and not authorization.observe
                or not set(permission['navigation']) <= set(authorization.navigation)
                or not requested_writes <= set(authorization.business_writes)):
            gaps.append('GAP_AUTHORIZATION_SCOPE')
        if type(authorization.model_requests) is not int or authorization.model_requests < scope['budgets']['max_model_requests']:
            gaps.append('GAP_MODEL_AUTHORIZATION')
    if not context.formal_gate_pass:
        gaps.append('GAP_ORIGINAL_FORMAL_GATE')
    return {
        'scope_id': scope['scope_id'], 'scope_hash': digest(scope),
        'status': 'BLOCKED' if gaps else 'OFFLINE_PREREQUISITES_CHECKED',
        'gaps': gaps, 'domain': target['domain'], 'execution_authority': False,
        'live_learning': 'NOT_IMPLEMENTED_IN_P2_1',
        'safe_independent_work': ['DEFINE_CONTRACT', 'AUDIT_LOCAL_MATERIAL', 'RECORD_HUMAN_COST', 'OFFLINE_TEST'],
    }
