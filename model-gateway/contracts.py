"""Strict two-boolean trace subset. Evidence and model output never grant approval."""
import json
import re
import uuid

PACKAGES = ('edu.sydney.smarthomelab', 'edu.sydney.transferlab', 'edu.sydney.transferroom')
MAX_BYTES = 65536
TRACE_FIELDS = set('kind schemaVersion traceId appPackage appVersion goal source end observationScope visualEvidence steps finalState unattributedChanges unsupportedClicks overflowClicks'.split())
STEP_FIELDS = set('index targetId eventTime before after outcome'.split())


class ContractError(ValueError):
    """Stable reason code only; never includes input data or credentials."""


def require(condition, code):
    if not condition:
        raise ContractError(code)


def fields(value, expected):
    require(type(value) is dict and set(value) == set(expected), 'FIELDS')


def safe_text(value, limit):
    require(type(value) is str and 0 < len(value.strip()) <= limit
            and len(value) <= limit and all(ord(c) >= 32 and ord(c) != 127 for c in value)
            and not re.search(r'sk-[A-Za-z0-9_.-]{10,}|apikey_[A-Za-z0-9_]{10,}', value), 'TEXT')


def load_json(raw):
    require(type(raw) is str and len(raw.encode('utf-8')) <= MAX_BYTES, 'SIZE')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_KEY')
            result[key] = value
        return result
    def constant(_):
        raise ContractError('NONFINITE')
    try:
        result = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
        require(type(result) is dict, 'OBJECT_REQUIRED')
        return result
    except (ValueError, RecursionError) as exc:
        raise ContractError('INVALID_JSON') from None


def validate_trace(trace):
    fields(trace, TRACE_FIELDS)
    require(trace['kind'] == 'TRACE_BUNDLE' and type(trace['schemaVersion']) is int
            and trace['schemaVersion'] == 1, 'TRACE_VERSION')
    pkg = trace['appPackage']
    require(type(pkg) is str and pkg in PACKAGES, 'APP_NOT_ALLOWED')
    try:
        require(str(uuid.UUID(trace['traceId'])) == trace['traceId'], 'TRACE_ID')
    except (ValueError, TypeError, AttributeError):
        raise ContractError('TRACE_ID') from None
    safe_text(trace['appVersion'], 80); safe_text(trace['goal'], 240)
    require(trace['source'] in ('UNKNOWN', 'HUMAN_DECLARED', 'ADB_TEST'), 'SOURCE')
    require(trace['end'] == 'STOPPED', 'TRACE_NOT_STOPPED')
    require(trace['observationScope'] == 'TARGET_STATES_ONLY'
            and trace['visualEvidence'] == 'NOT_COLLECTED', 'UNSUPPORTED_SCOPE')
    for name in ('unattributedChanges', 'unsupportedClicks', 'overflowClicks'):
        require(type(trace[name]) is int and trace[name] == 0, 'INCOMPLETE_TRACE')
    steps, final = trace['steps'], trace['finalState']
    require(type(steps) is list and len(steps) == 2, 'TWO_STEPS_REQUIRED')
    require(type(final) is dict and len(final) <= 100, 'FINAL_STATE')
    ids, last = [], -1
    def valid_id(value):
        return type(value) is str and re.fullmatch(re.escape(pkg) + r':id/[A-Za-z0-9_]{1,80}', value)
    for index, step in enumerate(steps, 1):
        fields(step, STEP_FIELDS)
        require(type(step['index']) is int and step['index'] == index, 'STEP_ORDER')
        require(valid_id(step['targetId']) and step['targetId'] not in ids, 'TARGET_ID')
        require(type(step['eventTime']) is int and 0 <= step['eventTime'] <= 2**63-1
                and last <= step['eventTime'], 'EVENT_TIME')
        require(step['before'] in ('checked=false', 'checked=true')
                and step['after'] in ('checked=false', 'checked=true')
                and step['before'] != step['after'] and step['outcome'] == 'CHANGED', 'UNVERIFIED_STEP')
        require(final.get(step['targetId']) == step['after'], 'FINAL_GOAL_MISMATCH')
        ids.append(step['targetId']); last = step['eventTime']
    for key, value in final.items():
        # Unused range fields are intentionally outside this first compiler subset.
        require(valid_id(key) and value in ('checked=false', 'checked=true'), 'FINAL_STATE')
    return trace


def validate_draft(draft, trace):
    validate_trace(trace)
    fields(draft, ('status', 'reason', 'steps'))
    require(draft['status'] in ('candidate', 'clarify', 'reject'), 'DRAFT_STATUS')
    safe_text(draft['reason'], 400)
    require(type(draft['steps']) is list, 'DRAFT_STEPS')
    if draft['status'] != 'candidate':
        require(not draft['steps'], 'NONCANDIDATE_STEPS')
        return draft
    require(len(draft['steps']) == 2, 'TWO_STEPS_REQUIRED')
    for index, step in enumerate(draft['steps'], 1):
        fields(step, ('sourceIndex', 'role', 'desired'))
        require(type(step['sourceIndex']) is int and step['sourceIndex'] == index, 'EVIDENCE_ORDER')
        safe_text(step['role'], 80)
        require(type(step['desired']) is bool and step['desired'] ==
                (trace['steps'][index-1]['after'] == 'checked=true'), 'MODEL_CHANGED_GOAL')
    return draft


def to_v2(draft, trace):
    validate_draft(draft, trace)
    require(draft['status'] == 'candidate', 'NOT_CANDIDATE')
    return dict(schemaVersion=2, operation='SET_TWO_CHECKED', appPackage=trace['appPackage'],
                steps=[dict(resourceId=s['targetId'], before=s['before'] == 'checked=true',
                            after=s['after'] == 'checked=true') for s in trace['steps']])
