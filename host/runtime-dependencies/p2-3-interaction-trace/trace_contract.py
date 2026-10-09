"""Value-only interaction evidence. Never grants Android or task authority."""
import uuid
from p23deps import (plain_copy, identifier, digest, validate_observation,
                     derive_page, ObservationError, VALID)

SOURCES = ('HUMAN_DEMONSTRATION', 'AGENT_NAVIGATION', 'AGENT_BUSINESS_EXECUTION',
           'EVALUATOR_INITIALIZATION', 'UNKNOWN')
KINDS = ('CLICK', 'BACK', 'SCROLL')
CHANNEL = 'OFFLINE_CONTROLLED_TRAJECTORY'
MAX_STEPS = 128


class TraceError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def need(condition, code='INVALID_TRACE'):
    if not condition:
        raise TraceError(code)


def detached(value):
    try:
        return plain_copy(value)
    except ObservationError as error:
        raise TraceError('INVALID_TRACE_DTO') from error


def observation(value):
    try:
        return validate_observation(value)
    except (ObservationError, TypeError, KeyError, ValueError) as error:
        raise TraceError('INVALID_OBSERVATION') from error


def _id(value):
    return identifier(value) and all(c.isalnum() or c in '_.:-' for c in value)


def target_for(page):
    need(type(page) is dict and page.get('kind') == 'PageEvidence'
         and page.get('identity_status') == 'KNOWN', 'IDENTITY_UNCONFIRMED')
    return {'page_instance_id': page['page_instance_id'],
            'entity_keys': sorted(e['entity_key'] for e in page['entities']),
            'navigation_context': detached(page['navigation_context'])}


def check_target(value):
    if value is None:
        return None
    target = detached(value)
    need(type(target) is dict and set(target) == {'page_instance_id', 'entity_keys', 'navigation_context'}
         and _id(target['page_instance_id']), 'INVALID_TARGET')
    need(type(target['entity_keys']) is list and 0 < len(target['entity_keys']) <= 32
         and all(_id(v) for v in target['entity_keys'])
         and len(set(target['entity_keys'])) == len(target['entity_keys']), 'INVALID_TARGET')
    nav = target['navigation_context']
    need(type(nav) is dict and set(nav) == {'tab', 'popup', 'expanded', 'entry', 'visible_slice', 'page_hint'},
         'INVALID_TARGET')
    need(all(identifier(nav[k], nullable=True) for k in nav if k != 'expanded')
         and type(nav['expanded']) is list and len(nav['expanded']) <= 128
         and all(identifier(v) for v in nav['expanded']), 'INVALID_TARGET')
    return target


def matches_target(page, target):
    return target is not None and page.get('identity_status') == 'KNOWN' and target_for(page) == target


def check_action(value, before):
    action = detached(value)
    need(type(action) is dict and set(action) == {'kind', 'semantic_target', 'node_local_id'}
         and action['kind'] in KINDS and identifier(action['semantic_target'])
         and _id(action['node_local_id']), 'INVALID_ACTION')
    need(before['capture_status'] in VALID, 'PRE_OBSERVATION_UNAVAILABLE')
    nodes = [n for n in before['tree']['nodes'] if n['node_local_id'] == action['node_local_id']]
    need(len(nodes) == 1 and nodes[0]['visible'] and nodes[0]['enabled'], 'STALE_OR_MISSING_CANDIDATE')
    node = nodes[0]
    clues = {key: node[key] for key in ('resource_id', 'role', 'text', 'content_description', 'class_name', 'bounds')}
    return action, clues


def check_receipt(value, before, after):
    receipt = detached(value)
    need(type(receipt) is dict and set(receipt) == {
        'dispatch_id', 'status', 'started_elapsed_ms', 'finished_elapsed_ms', 'clock_domain',
        'channel', 'error_code'}, 'INVALID_RECEIPT')
    need(_id(receipt['dispatch_id']) and receipt['channel'] == CHANNEL
         and receipt['status'] in ('SENT_SIMULATED', 'OBSERVED_INPUT_SIMULATED', 'NOT_SENT', 'UNKNOWN')
         and receipt['clock_domain'] == 'elapsedRealtime'
         and identifier(receipt['error_code'], nullable=True), 'INVALID_RECEIPT')
    start, end = receipt['started_elapsed_ms'], receipt['finished_elapsed_ms']
    need(type(start) is int and type(end) is int and 0 <= before['ended_elapsed_ms'] <= start <= end,
         'DISPATCH_TIME_ERROR')
    if after is not None:
        need(end <= after['started_elapsed_ms'], 'DISPATCH_TIME_ERROR')
    return receipt


def check_write_audit(value):
    audit = detached(value)
    need(type(audit) is dict and set(audit) == {'coverage', 'committed', 'pending', 'evidence_ref', 'channel'},
         'INVALID_WRITE_AUDIT')
    need(audit['coverage'] in ('COMPLETE', 'INCOMPLETE', 'UNAVAILABLE')
         and audit['channel'] == 'DECLARED_FIXTURE_JOURNAL'
         and identifier(audit['evidence_ref'], nullable=True), 'INVALID_WRITE_AUDIT')
    need(all(type(audit[k]) is int and 0 <= audit[k] <= 100000 for k in ('committed', 'pending')),
         'INVALID_WRITE_AUDIT')
    need(audit['coverage'] != 'COMPLETE' or audit['evidence_ref'] is not None, 'INVALID_WRITE_AUDIT')
    return audit


def describe_changes(pre, post):
    if post is None:
        return {'page_changed': None, 'entity_changed': None, 'view_changed': None,
                'dynamic_changed': None, 'unknowns': ['POST_OBSERVATION_UNAVAILABLE']}
    return {'page_changed': pre['page_instance_id'] != post['page_instance_id'],
            'entity_changed': sorted(e['entity_key'] for e in pre['entities']) != sorted(e['entity_key'] for e in post['entities']),
            'view_changed': pre['view_slice_id'] != post['view_slice_id'],
            'dynamic_changed': [{k: v for k, v in d.items() if k != 'evidence_ref'} for d in pre['dynamic_state']]
                               != [{k: v for k, v in d.items() if k != 'evidence_ref'} for d in post['dynamic_state']],
            'unknowns': [] if pre['identity_status'] == post['identity_status'] == 'KNOWN' else ['IDENTITY_UNCONFIRMED']}


def business_state_conflict(pre, post):
    """Compare only uniquely attributable typed business controls visible in both observations.

    Newly discovered controls are not assumed to have changed; selected Tab state is navigation.
    This is a consistency check, not an independent oracle or a complete write detector.
    """
    def states(page):
        if page is None:
            return {}
        elements = {e['node_local_id']: e for e in page['elements']}
        values = {}
        for state in page['dynamic_state']:
            element = elements[state['evidence_ref']['node_local_id']]
            if state['field'] not in ('checked', 'range.value') or not element['resource_id'] or not element['entity_key']:
                continue
            key = (element['entity_key'], element['resource_id'], element['role'], state['field'])
            values.setdefault(key, []).append(state['value'])
        return {key: value[0] for key, value in values.items() if len(value) == 1}
    a, b = states(pre), states(post)
    return any(a[k] != b[k] for k in a.keys() & b.keys())


def make_interaction(source, before, after, action, receipt, business_audit, *,
                     entity_types, expected_target=None, interaction_id=None, outcome_error=None):
    need(type(source) is str and source in SOURCES, 'INVALID_SOURCE')
    before = observation(before)
    after = observation(after) if after is not None else None
    action, clues = check_action(action, before)
    receipt = check_receipt(receipt, before, after)
    audit, expected = check_write_audit(business_audit), check_target(expected_target)
    need(identifier(outcome_error, nullable=True), 'INVALID_OUTCOME')
    interaction_id = interaction_id or str(uuid.uuid4())
    need(_id(interaction_id), 'INVALID_INTERACTION_ID')
    pre = derive_page(before, entity_types=entity_types)
    post = derive_page(after, entity_types=entity_types) if after is not None else None
    if after is not None:
        keys = ('environment', 'scope_hash', 'host_device_id', 'boot_session_id', 'observer_session_id')
        need(all(before[k] == after[k] for k in keys)
             and before['budget']['session_id'] == after['budget']['session_id'], 'OBSERVATION_CONTEXT_CHANGED')
        need(before['observation_id'] != after['observation_id'], 'OBSERVATION_REUSED')
    changes = describe_changes(pre, post)
    status = 'UNCONFIRMED'
    unknowns = list(changes['unknowns'])
    failure = outcome_error or receipt['error_code']
    if failure:
        status = 'CANCELLED' if failure == 'CANCELLED' else 'TIMEOUT' if failure == 'TIMEOUT' else 'FAILED'
    elif audit['committed'] or audit['pending']:
        status = 'SAFETY_VIOLATION' if source == 'AGENT_NAVIGATION' else 'OBSERVED_WITH_WRITES'
        failure = 'UNAUTHORIZED_OR_PENDING_WRITE' if source == 'AGENT_NAVIGATION' else None
    elif audit['coverage'] != 'COMPLETE':
        unknowns.append('BUSINESS_EFFECT_UNKNOWN')
    elif source == 'AGENT_NAVIGATION' and business_state_conflict(pre, post):
        unknowns.append('BUSINESS_STATE_CHANGED_WITHOUT_AUDIT')
    elif receipt['status'] not in ('SENT_SIMULATED', 'OBSERVED_INPUT_SIMULATED'):
        unknowns.append('DISPATCH_UNCONFIRMED')
    elif post is not None and post['identity_status'] == pre['identity_status'] == 'KNOWN':
        if not changes['page_changed']:
            status = 'NO_TRANSITION'
        elif source in ('HUMAN_DEMONSTRATION', 'AGENT_NAVIGATION') and matches_target(post, expected):
            status = 'ARRIVAL_VERIFIED_SIMULATED'
        else:
            status = 'OBSERVED_SIMULATED'
            if expected is not None and not matches_target(post, expected):
                failure = 'ARRIVAL_MISMATCH'
    return detached({
        'kind': 'InteractionEvidence', 'schema_version': '1.0', 'interaction_id': interaction_id,
        'channel': CHANNEL, 'source': source, 'source_assurance': 'DECLARED_FIXTURE_NOT_ACTOR_AUTHENTICATION',
        'action': action, 'public_clues': clues,
        'before': {'observation_id': before['observation_id'], 'sha256': digest(before), 'page': pre},
        'after': None if after is None else {'observation_id': after['observation_id'], 'sha256': digest(after), 'page': post},
        'dispatch': receipt, 'business_audit': audit, 'expected_target': expected,
        'changes': changes, 'status': status, 'failure_code': failure,
        'outcome_error': outcome_error, 'unknowns': sorted(set(unknowns)),
        'evidence_level': 'NOT_REAL_ANDROID_EVIDENCE', 'execution_authority': False})


def validate_interaction(value, before, after, entity_types):
    step = detached(value)
    need(type(step) is dict and step.get('kind') == 'InteractionEvidence', 'INVALID_INTERACTION')
    try:
        expected = make_interaction(step['source'], before, after, step['action'], step['dispatch'],
                                    step['business_audit'], entity_types=entity_types,
                                    expected_target=step['expected_target'], interaction_id=step['interaction_id'],
                                    outcome_error=step['outcome_error'])
    except (KeyError, TypeError) as error:
        raise TraceError('INVALID_INTERACTION') from error
    need(step == expected, 'INTERACTION_EVIDENCE_MISMATCH')
    return expected
