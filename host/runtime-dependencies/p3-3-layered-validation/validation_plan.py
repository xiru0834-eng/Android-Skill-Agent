"""Derive a bounded inert validation matrix from compiled entity capability domains."""
import copy
import math
from p33deps import compiler, environment, contracts, digest
from layered_validation import format_layer


def samples(spec, target):
    domain = target['domain']
    if 'values' in domain:
        values = domain['values']
    else:
        low, high, step = domain['min'], domain['max'], domain['step']
        # Intersection of the input lattice and the entity lattice, without
        # enumerating large domains or clipping an invalid request.
        spec_low = spec.get('minimum', low); spec_high = spec.get('maximum', high)
        spec_step = spec.get('step', 1)
        common = math.gcd(step, spec_step)
        if (spec_low - low) % common:
            return []
        modulus = spec_step // common
        offset = 0 if modulus == 1 else (((spec_low - low) // common * pow(step // common, -1, modulus)) % modulus)
        base = low + step * offset
        stride = math.lcm(step, spec_step)
        lower, upper = max(low, spec_low), min(high, spec_high)
        first = base + ((lower - base + stride - 1) // stride) * stride
        if first > upper: return []
        last = first + ((upper - first) // stride) * stride
        values = list(dict.fromkeys([first, last, first + ((last - first) // stride // 2) * stride,
                                     min(last, first + stride), max(first, last - stride)]))
    valid = []
    for value in values:
        try:
            contracts._value_domain(value, spec)
            valid.append(value)
        except contracts.ContractError:
            pass
    return valid


def build_validation_plan(flow, package, demonstration_task, profile=None):
    receipt, compiled = format_layer(flow, package, demonstration_task, profile)
    out = {'kind': 'FlowValidationPlan', 'schema_version': '1.0', 'status': 'REJECTED',
           'format_receipt': receipt, 'cases': [], 'parameter_values': {},
           'execution_authority': False, 'device_execution_verified': False,
           'verified_values': [], 'parameter_domain_verified': False,
           'evidence_channel': 'PLAN_NOT_EXECUTED', 'repetitions': 3}
    if compiled is None:
        return out
    data = compiled.to_dict()
    out['blocking_unknowns'] = copy.deepcopy(data['blocking_unknowns'])
    env = (profile or environment.audited_room_profile()).to_dict()
    specs = {s['name']: s for s in flow['inputs']}
    task = copy.deepcopy(demonstration_task)
    initial = {key: samples(contracts.CAPS[target['skill']], target)[0]
               for key, target in env['targets'].items()}

    def add(category, inputs, states, expected, fault=None):
        case = {'category': category, 'task_inputs': copy.deepcopy(inputs),
                'frozen_initial_state': copy.deepcopy(states), 'expected': expected,
                'fault': fault, 'reset_to_frozen_initial': True, 'repetitions': 3,
                'channel': 'NOT_EXECUTED', 'requires_authorized_native_runtime': True}
        case['case_id'] = 'case.' + digest(case)[:24]
        if case['case_id'] not in {row['case_id'] for row in out['cases']}:
            out['cases'].append(case)

    for source_step, step in zip(flow['steps'], data['steps']):
        if step['op'] != 'CALL' or source_step['argument']['kind'] != 'input':
            continue
        name = source_step['argument']['name']; spec = specs[name]
        value = task['inputs'][name]; target = env['targets'][step['target_key']]
        # One input used with incompatible targets is intentionally not guessed.
        if name in out['parameter_values']:
            if out['parameter_values'][name]['target_key'] != step['target_key']:
                out.update(status='UNCONFIRMED_PLAN_DERIVATION', cases=[])
                return out
            continue
        values = samples(spec, target)
        unseen = [v for v in values if type(v) is not type(value) or v != value][:2]
        out['parameter_values'][name] = {'demonstration': value, 'unseen_legal': unseen,
            'target_key': step['target_key'], 'unit': target['unit'], 'domain': copy.deepcopy(target['domain']),
            'coverage_note': 'AT_LEAST_TWO_UNSEEN' if len(unseen) >= 2 else 'SMALL_DOMAIN_EXHAUSTED'}
        add('DEMONSTRATION', task['inputs'], initial, 'VERIFY_TARGET_AND_PRESERVE')
        for v in unseen:
            inputs = dict(task['inputs'], **{name: v})
            add('UNSEEN_LEGAL', inputs, initial, 'VERIFY_TARGET_AND_PRESERVE')
        same_target = unseen[0] if unseen else value
        for v in list(dict.fromkeys(values + [value]))[:4]:
            states = dict(initial, **{step['target_key']: v})
            add('DIFFERENT_INITIAL', dict(task['inputs'], **{name: same_target}), states, 'VERIFY_TARGET_AND_PRESERVE')
        add('ALREADY_SATISFIED', task['inputs'], dict(initial, **{step['target_key']: value}),
            'ONLY_SKIP_CALLS_ALREADY_SATISFIED_NOT_EXPLICIT_INTERMEDIATE_ACTIONS')
        bad_values = [None, True, 'invalid']
        if spec['type'] == 'integer':
            bad_values += [spec['minimum'] - 1, spec['maximum'] + 1]
        for v in bad_values:
            add('ILLEGAL_PARAMETER', dict(task['inputs'], **{name: v}), initial, 'REJECTED_ZERO_INPUTS')
        add('INPUT_NO_EFFECT', task['inputs'], initial, 'UNCONFIRMED_NOT_SUCCESS', 'ACK_WITHOUT_EFFECT')
    add('AMBIGUOUS_ENTITY', task['inputs'], initial, 'BLOCKED_ZERO_INPUTS', 'MULTIPLE_ENTITY_CANDIDATES')
    out['status'] = 'PLANNED_NOT_EXECUTED' if out['parameter_values'] else 'UNCONFIRMED_PLAN_DERIVATION'
    out['plan_hash'] = digest(data)
    out['limitations'] = ['BOUNDED_SAMPLES_NOT_FULL_DOMAIN', 'NO_LIVE_ENTITY_LOCATOR',
                          'FAULT_INJECTION_REQUIRES_ISOLATED_TEST_HARNESS', 'INITIAL_STATE_IS_PLANNED_NOT_MEASURED']
    return out
