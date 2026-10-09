"""Pure dynamic checks. Trusted host data is not supplied by Flow/model JSON.

No device calls and no permissions are created here. Native input guards remain
mandatory even after these checks. Observe/dispatch integration is P1.4 work.
"""
from dataclasses import dataclass
import json
from compiler import CompileError, require
from dependencies import contracts as old, digest
from compilation_context import check_entity_value
from compiler import checked

MAX_OBSERVATION_AGE_MS = 500  # Offline check contract, not a claim of native atomic UI reads.
UNKNOWN = object()

@dataclass(frozen=True)
class PolicyContext:
    plan_hash: str
    host_device_id: str
    environment_hash: str
    authorization_ref: str
    cancellation_token_ref: str
    allowed_writes: frozenset
    started_ms: int
    deadline_ms: int
    max_actions: int
    local_approval_verified: bool
    approved_raw_package_hash: str
    source: str = 'TEST_FIXTURE_NOT_NATIVE_APPROVAL'
    cancelled: bool = False
    revoked: bool = False
    estimated_required_ms: int | None = None
    observation_session_id: str = ''

@dataclass(frozen=True)
class Observation:
    task_id: str
    host_device_id: str
    environment_hash: str
    phase: str
    sequence: int
    captured_ms: int
    values_json: str
    observation_session_id: str = ''

def check_task_policy(plan, policy, now_ms):
    data = plan.to_dict()
    def need(ok, code, path='$.authorization_ref'):
        require(ok, code, path, 'PERMISSION')
    need(type(policy) is PolicyContext, 'POLICY_CONTEXT_UNAVAILABLE')
    need(type(policy.cancelled) is bool and type(policy.revoked) is bool and
         type(policy.local_approval_verified) is bool and type(policy.allowed_writes) is frozenset,
         'POLICY_CONTEXT_INVALID')
    need(policy.source in ('TEST_FIXTURE_NOT_NATIVE_APPROVAL', 'TRUSTED_HOST_ADAPTER'), 'POLICY_CONTEXT_INVALID')
    need(type(policy.observation_session_id) is str and 0 < len(policy.observation_session_id) <= 128, 'POLICY_CONTEXT_INVALID')
    need(not policy.cancelled, 'CANCELLED')
    need(not policy.revoked, 'PERMISSION_REVOKED')
    need(policy.plan_hash == digest(data) and policy.host_device_id == data['host_device_id'] and
         policy.environment_hash == data['environment_hash'] and policy.authorization_ref == data['authorization_ref'] and
         policy.cancellation_token_ref == data['cancellation_token_ref'], 'POLICY_BINDING_MISMATCH')
    need(policy.local_approval_verified and policy.approved_raw_package_hash == data['source_package_raw_hash'], 'LOCAL_REVIEW_REQUIRED')
    for index, step in enumerate(data['steps']):
        if step['op'] == 'CALL':
            need(step['target_key'] in policy.allowed_writes, 'PERMISSION_DENIED', f'$.steps[{index}]')
    need(not data['blocking_unknowns'], 'BLOCKING_UNKNOWN', '$.unknowns')
    for value in (now_ms, policy.started_ms, policy.deadline_ms, policy.max_actions):
        need(type(value) is int and value >= 0, 'POLICY_CONTEXT_INVALID', '$.budget')
    requested = data['task_budget']
    duration = policy.deadline_ms - policy.started_ms
    need(1 <= duration <= data['whole_budget_limit_ms'] and
         requested['duration_ms'] <= data['whole_budget_limit_ms'] and duration <= requested['duration_ms'],
         'BUDGET_LIMIT_EXCEEDED', '$.budget.duration_ms')
    need(policy.started_ms <= now_ms < policy.deadline_ms, 'BUDGET_INSUFFICIENT', '$.budget.duration_ms')
    need(data['call_count'] <= min(policy.max_actions, requested['max_actions'], 32),
         'BUDGET_INSUFFICIENT', '$.budget.max_actions')
    estimate = policy.estimated_required_ms
    need(estimate is None or (type(estimate) is int and estimate >= 0), 'POLICY_CONTEXT_INVALID', '$.budget')
    need(estimate is None or estimate <= policy.deadline_ms - now_ms, 'BUDGET_INSUFFICIENT', '$.budget.duration_ms')
    return dict(permission_state='CHECKED_TEST_FIXTURE' if policy.source.startswith('TEST_FIXTURE') else 'CHECKED_HOST_POLICY',
                execution_authority=False, ready_for_device_execution=False, deadline_ms=policy.deadline_ms,
                remaining_ms=policy.deadline_ms - now_ms, model_calls=0,
                duration_estimate_status='NOT_EVALUATED' if estimate is None else 'TRUSTED_ADAPTER_ESTIMATE_NOT_MEASUREMENT')


def valid_observation(plan, frame, phase, now_ms, min_sequence=0, historical=False):
    data = plan.to_dict()
    if type(frame) is not Observation or any(type(v) is not int for v in (now_ms, frame.captured_ms, frame.sequence, min_sequence)):
        return False
    return (frame.task_id == data['task_id'] and frame.host_device_id == data['host_device_id'] and
            frame.environment_hash == data['environment_hash'] and frame.phase == phase and
            type(frame.observation_session_id) is str and 0 < len(frame.observation_session_id) <= 128 and
            frame.sequence > min_sequence and 0 <= frame.captured_ms <= now_ms and
            (historical or now_ms - frame.captured_ms <= MAX_OBSERVATION_AGE_MS))


def observed_value(plan, frame, key):
    data = plan.to_dict()
    if key not in data['state_contracts']:
        return UNKNOWN
    try:
        values = old.parse_document(frame.values_json)
        if type(values) is not dict or key not in values:
            return UNKNOWN
        value = values[key]
        specification = data['state_contracts'][key]
        old._value_domain(value, old.CAPS[specification['skill']])
        domain = specification['domain']
        valid = (value in domain['values'] if 'values' in domain else
                 domain['min'] <= value <= domain['max'] and (value - domain['min']) % domain['step'] == 0)
        return value if valid else UNKNOWN
    except (old.ContractError, ValueError, TypeError):
        return UNKNOWN


@dataclass(frozen=True)
class ReadEvidence:
    step_id: str
    frame: Observation


def value_of(plan, expression, frame, phase, now_ms, initial=None, reads=None):
    kind = expression['kind']
    if kind == 'literal':
        return expression['value']
    if kind == 'state':
        return observed_value(plan, frame, expression['key'])
    if kind == 'initial':
        if (not valid_observation(plan, initial, 'ENTRY', now_ms, historical=True) or initial.sequence > frame.sequence or
            initial.observation_session_id != frame.observation_session_id):
            return UNKNOWN
        return observed_value(plan, initial, expression['key'])
    evidence = (reads or {}).get(expression['step_id'])
    steps = plan.to_dict()['steps']
    order = {s['id']: i for i, s in enumerate(steps)}
    if (type(evidence) is not ReadEvidence or evidence.step_id != expression['step_id'] or
        expression['step_id'] not in order or steps[order[expression['step_id']]]['op'] != 'READ' or
        order[expression['step_id']] >= order.get(phase, len(steps) if phase == 'FINAL' else -1) or
        not valid_observation(plan, evidence.frame, evidence.step_id, now_ms, historical=True) or
        evidence.frame.observation_session_id != frame.observation_session_id or
        evidence.frame.sequence >= frame.sequence):
        return UNKNOWN
    return observed_value(plan, evidence.frame, steps[order[expression['step_id']]]['target_key'])

def evaluate_predicate(plan, predicate, observation, phase, now_ms, initial=None, reads=None, min_sequence=0):
    if not valid_observation(plan, observation, phase, now_ms, min_sequence):
        return 'UNKNOWN'
    if predicate['op'] == 'known':
        value = value_of(plan, predicate['value'], observation, phase, now_ms, initial, reads)
        return 'UNKNOWN' if value is UNKNOWN else 'TRUE'
    left = value_of(plan, predicate['left'], observation, phase, now_ms, initial, reads)
    right = value_of(plan, predicate['right'], observation, phase, now_ms, initial, reads)
    if left is UNKNOWN or right is UNKNOWN:
        return 'UNKNOWN'
    return 'TRUE' if type(left) is type(right) and left == right else 'FALSE'


def materialize_call(plan, index, observation, policy, now_ms, initial=None, reads=None, min_sequence=0):
    permission = check_task_policy(plan, policy, now_ms)
    data = plan.to_dict()
    require(type(index) is int and 0 <= index < len(data['steps']), 'BAD_REFERENCE', '$.step_index', 'FLOW')
    step = data['steps'][index]
    path = f'$.steps[{index}]'
    require(step['op'] == 'CALL', 'NOT_A_CALL', path, 'FLOW')
    require(valid_observation(plan, observation, step['id'], now_ms, min_sequence),
            'OBSERVATION_UNAVAILABLE', path, 'CONDITIONS')
    require(observation.observation_session_id == policy.observation_session_id,
            'OBSERVATION_UNAVAILABLE', path, 'CONDITIONS')
    value = value_of(plan, step['value'], observation, step['id'], now_ms, initial, reads)
    require(value is not UNKNOWN, 'DYNAMIC_VALUE_UNKNOWN', path + '.argument', 'CONDITIONS')
    check_entity_value(value, old.CAPS[step['skill']], step['domain'], path + '.argument', require, checked)
    current = observed_value(plan, observation, step['target_key'])
    require(current is not UNKNOWN, 'CURRENT_VALUE_UNKNOWN', path, 'CONDITIONS')
    return dict(status='CALL_DATA_READY', execution_authority=False, ready_for_device_execution=False,
                step_id=step['id'], call={'skill': step['skill'], 'args': {'device': step['entity_id'], step['argument']: value}},
                skip_business_input=type(current) is type(value) and current == value,
                permission_check=permission, deadline_ms=permission['deadline_ms'], business_action_retries=0)
