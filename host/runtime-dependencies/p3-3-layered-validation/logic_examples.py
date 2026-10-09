"""Confirmation harness: dictionary writes only, explicitly HANDWRITTEN_TEST_FIXTURE."""
import copy
from test_validation import bundle, LogicRunTests, support
from p33deps import compiler
from validation_plan import build_validation_plan
from evaluator import score_execution


def collect_examples():
    outputs = []
    harness = LogicRunTests()
    for skill, value in (('SetBrightness', 60), ('SetTemperature', 22), ('SetPower', 'on')):
        flow, package, task = bundle(value, skill)
        matrix = build_validation_plan(flow, package, task)
        cases = [c for c in matrix['cases'] if c['category'] in ('DEMONSTRATION', 'UNSEEN_LEGAL', 'ALREADY_SATISFIED')]
        for case in cases:
            changed = copy.deepcopy(task); changed['inputs'] = case['task_inputs']
            events = []
            def callback(port, call):
                cap = compiler.old.CAPS[call['skill']]
                key = call['args']['device'] + '.' + cap['property']; value = call['args'][cap['argument']]
                port.apply(call)
                events.append({'step_id': 'set_value', 'target_key': key, 'value': value,
                               'submitted': True, 'effective': type(port.state[key]) is type(value) and port.state[key] == value})
                return {'final_status': 'SUCCESS', 'verification_result': True}
            result, port, plan = harness.run_case(flow, package, changed, case['frozen_initial_state'], on_call=callback)
            score = score_execution(plan, result.receipt, case['frozen_initial_state'], port.state, events)
            outputs.append({'channel': 'HANDWRITTEN_LOGIC_SIMULATION_NOT_LEARNED_OR_ANDROID',
                'skill': skill, 'category': case['category'], 'task_inputs': changed['inputs'],
                'initial_state': case['frozen_initial_state'], 'final_state': port.state,
                'write_events': events, 'public_receipt': result.receipt,
                'runtime_scope': result.evidence.to_dict() if result.evidence else None,
                'independent_logic_score': score, 'example_not_formal_device_case': True})
    return outputs
