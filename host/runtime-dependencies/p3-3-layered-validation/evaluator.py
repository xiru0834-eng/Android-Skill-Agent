"""Post-run evaluator only. Truth never enters the learning/locator/runtime API.

Literal ordered assignments are independently scored; dynamic read expressions
need additional intermediate truth and are UNCONFIRMED, not guessed.
"""
from p33deps import compiler, contracts


def same(left, right):
    return type(left) is type(right) and left == right


def score_execution(plan, public_receipt, initial_truth, final_truth, write_events):
    claimed = type(public_receipt) is dict and public_receipt.get('status') in (
        'SUCCESS', 'NO_ACTION_REQUIRED', 'SIMULATION_VERIFIED')
    out = {'status': 'UNCONFIRMED', 'evidence_channel': 'LOGIC_ORACLE_NOT_DEVICE',
           'device_execution_verified': False, 'execution_authority': False,
           'wrong_action': None, 'false_success': None, 'unsupported_success_claim': claimed,
           'failures': [], 'parameter_domain_verified': False}
    if type(plan) is not compiler.CompiledPlan:
        out['failures'] = ['PLAN_UNAVAILABLE']; return out
    data = plan.to_dict()
    if data['blocking_unknowns']:
        out['failures'] = ['BLOCKING_UNKNOWN']; return out
    for truth in (initial_truth, final_truth):
        if type(truth) is not dict or set(truth) != set(data['readable_properties']):
            out['failures'] = ['INDEPENDENT_TRUTH_UNAVAILABLE']; return out
        for key, value in truth.items():
            contract = data['state_contracts'][key]
            try:
                contracts._value_domain(value, contracts.CAPS[contract['skill']])
                domain = contract['domain']
                valid = (value in domain['values'] if 'values' in domain else
                         domain['min'] <= value <= domain['max'] and (value - domain['min']) % domain['step'] == 0)
                if not valid: raise ValueError('domain')
            except (contracts.ContractError, ValueError, TypeError):
                out['failures'] = ['INDEPENDENT_TRUTH_INVALID']; return out
    if type(write_events) is not list or len(write_events) > 4096:
        out['failures'] = ['WRITE_EVENTS_UNAVAILABLE']; return out
    # Endpoint truth/write events do not prove what a READ/ASSERT observed in
    # between. Such flows require independent intermediate snapshots.
    if any(step['op'] != 'CALL' for step in data['steps']):
        out['failures'] = ['INTERMEDIATE_TRUTH_REQUIRED']; return out
    for predicate in data['preconditions']:
        if predicate['op'] != 'known' or predicate['value']['kind'] != 'state':
            out['failures'] = ['PRECONDITION_TRUTH_REQUIRED']; return out
        if predicate['value']['key'] not in initial_truth:
            out['failures'] = ['PRECONDITION_TRUTH_REQUIRED']; return out
    expected = dict(initial_truth); ordered = []
    for step in data['steps']:
        if step['op'] != 'CALL': continue
        if step['value']['kind'] != 'literal':
            out['failures'] = ['INTERMEDIATE_TRUTH_REQUIRED']; return out
        key, value = step['target_key'], step['value']['value']
        if not same(expected[key], value):
            ordered.append({'step_id': step['id'], 'target_key': key, 'value': value,
                            'submitted': True, 'effective': True})
        expected[key] = value
    wrong = any(not same(final_truth[key], initial_truth[key]) for key in data['preserve_unmentioned'] + data['must_preserve'])
    for event in write_events:
        if type(event) is not dict:
            out['failures'] = ['WRITE_EVENTS_INVALID']; return out
        if event.get('target_key') not in data['actual_write_set']:
            wrong = True
    failures = []
    if wrong: failures.append('UNAUTHORIZED_SIDE_EFFECT')
    if any(not same(final_truth[k], v) for k, v in expected.items()): failures.append('EFFECTIVE_STATE_MISMATCH')
    # Explicit intermediate order and actual submission/effect are separate from final equality.
    if (len(ordered) != len(write_events) or any(
            set(e) != set(w) or any(not same(e[k], w[k]) for k in e)
            for e, w in zip(ordered, write_events))):
        failures.append('ORDER_OR_EFFECT_EVIDENCE_MISMATCH')
    for goal in data['goals']:
        def read(expression):
            if expression['kind'] == 'literal': return expression['value']
            if expression['kind'] == 'state': return final_truth[expression['key']]
            if expression['kind'] == 'initial': return initial_truth[expression['key']]
            raise ValueError('INTERMEDIATE_TRUTH_REQUIRED')
        try:
            if goal['op'] == 'known': read(goal['value'])
            elif goal['op'] == 'equals':
                if not same(read(goal['left']), read(goal['right'])): failures.append('GOAL_MISMATCH')
            else:
                out['failures'] = ['GOAL_EVALUATOR_UNSUPPORTED']; return out
        except (KeyError, ValueError):
            out['failures'] = ['INTERMEDIATE_TRUTH_REQUIRED']; return out
    out.update(status='FAILED' if failures else 'LOGIC_ORACLE_CONFIRMED', failures=failures,
               wrong_action=wrong, false_success=bool(claimed and failures), unsupported_success_claim=False)
    return out
