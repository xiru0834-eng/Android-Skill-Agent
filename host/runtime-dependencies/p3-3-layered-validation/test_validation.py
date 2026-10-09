"""Logic dictionary transport and separate evaluator, not device or learned-flow evidence."""
import copy
import tempfile
import unittest
from p33deps import (P14, trusted, p14, compiler, environment, records, flow_store, canonical)
from validation_plan import build_validation_plan
from validation_run import run_logic_validation
from evaluator import score_execution

support = trusted('test_support', P14)


def bundle(value=60, skill='SetBrightness'):
    return p14.fixture_bundle(skill, value)


class PlanTests(unittest.TestCase):
    def test_demo_two_unseen_and_different_initials_derived_from_actual_domain(self):
        f, p, t = bundle()
        out = build_validation_plan(f, p, t)
        self.assertEqual(out['status'], 'PLANNED_NOT_EXECUTED')
        values = out['parameter_values']['value']
        self.assertEqual(values['demonstration'], 60)
        self.assertGreaterEqual(len(values['unseen_legal']), 2)
        self.assertNotIn(60, values['unseen_legal'])
        self.assertTrue(all(0 <= v <= 100 for v in values['unseen_legal']))
        kinds = {c['category'] for c in out['cases']}
        self.assertTrue({'DEMONSTRATION', 'UNSEEN_LEGAL', 'DIFFERENT_INITIAL', 'ALREADY_SATISFIED',
                         'ILLEGAL_PARAMETER', 'AMBIGUOUS_ENTITY', 'INPUT_NO_EFFECT'} <= kinds)
        self.assertTrue(all(c['reset_to_frozen_initial'] for c in out['cases']))
        self.assertFalse(out['execution_authority'])

    def test_small_enum_domain_deduplicates_and_explains_shortfall(self):
        f, p, t = bundle('on', 'SetPower')
        out = build_validation_plan(f, p, t)
        self.assertEqual(out['parameter_values']['value']['unseen_legal'], ['off'])
        self.assertEqual(out['parameter_values']['value']['coverage_note'], 'SMALL_DOMAIN_EXHAUSTED')

    def test_temperature_uses_entity_not_brightness_domain(self):
        f, p, t = bundle(22, 'SetTemperature')
        out = build_validation_plan(f, p, t)
        self.assertTrue(all(16 <= v <= 30 for v in out['parameter_values']['value']['unseen_legal']))

    def test_illegal_demo_or_unknown_entity_does_not_generate_execution_plan(self):
        for value in (-1, 101, 'very bright', True, None):
            with self.subTest(value=value):
                f, p, t = bundle(); t['inputs']['value'] = value
                out = build_validation_plan(f, p, t)
                self.assertEqual(out['status'], 'REJECTED'); self.assertEqual(out['cases'], [])

    def test_plan_preserves_original_and_does_not_claim_full_domain(self):
        f, p, t = bundle(); before = copy.deepcopy((f, p, t))
        out = build_validation_plan(f, p, t)
        self.assertEqual((f, p, t), before)
        self.assertEqual(out['verified_values'], [])
        self.assertFalse(out['parameter_domain_verified'])

    def test_narrow_input_domain_still_finds_two_unseen_without_clipping(self):
        f, p, t = bundle(80)
        f['inputs'][1].update(minimum=78, maximum=82)
        out = build_validation_plan(f, p, t)
        self.assertEqual(out['status'], 'PLANNED_NOT_EXECUTED')
        self.assertEqual(len(out['parameter_values']['value']['unseen_legal']), 2)
        self.assertTrue(all(78 <= v <= 82 for v in out['parameter_values']['value']['unseen_legal']))

    def test_initial_state_is_validated_and_pending_unknowns_remain(self):
        f, p, t = bundle(80); f['unknowns'] = [{'id': 'unknown.control', 'description': 'not located', 'impact': 'BLOCKS_EXECUTION'}]
        out = build_validation_plan(f, p, t)
        self.assertIn('unknown.control', out['blocking_unknowns'])
        self.assertFalse(out['execution_authority'])


class LogicRunTests(unittest.TestCase):
    def run_case(self, flow, package, task, initial=None, on_call=None, policy_change=None, native=False):
        clock = support.Clock(); port = support.RoomPort(clock, initial)
        port.on_call = on_call
        if native: port.channel = 'ANDROID_NATIVE'
        with tempfile.TemporaryDirectory(prefix='p33-logic-') as directory:
            store = flow_store.FlowStore.create(directory)
            try:
                draft = store.save_draft(canonical(flow), package, 0)
                key = draft['key']; store.check(key, 1, task, None)
                plan = compiler.compile_flow(flow, package, task, None)
                policy = support.policy_for(plan, **(policy_change or {}))
                result = run_logic_validation(store, key, task, records.ValidationAuthority(key, 'fixture.operator', True),
                                              lambda: policy, port, clock=clock)
                return result, port, plan
            finally: store.close()

    def test_repeat_restores_initial_and_uses_existing_cursor(self):
        f, p, t = bundle(80)
        for repeat in range(3):
            with self.subTest(repeat=repeat):
                result, port, _ = self.run_case(f, p, t, support.STATE)
                self.assertEqual(result.receipt['status'], 'SIMULATION_VERIFIED')
                self.assertEqual(len(port.calls), 1)
                self.assertEqual(result.evidence.to_dict()['initial_state'], support.STATE)
                self.assertFalse(result.receipt['device_execution_verified'])

    def test_already_satisfied_reads_but_does_not_dispatch(self):
        f, p, t = bundle(80); initial = dict(support.STATE, **{'bedroom_light.brightnessPercent': 80})
        result, port, _ = self.run_case(f, p, t, initial)
        self.assertEqual(result.receipt['status'], 'SIMULATION_VERIFIED')
        self.assertEqual(len(port.calls), 0); self.assertGreater(len(port.observations), 0)

    def test_no_effect_cannot_be_verified(self):
        f, p, t = bundle(80)
        result, port, _ = self.run_case(f, p, t, on_call=lambda *_: {'final_status': 'SUCCESS', 'verification_result': True})
        self.assertNotEqual(result.receipt['status'], 'SIMULATION_VERIFIED')
        self.assertIsNone(result.evidence); self.assertEqual(len(port.calls), 1)

    def test_unmentioned_write_and_draft_ack_fail(self):
        f, p, t = bundle(80)
        def side_effect(port, call):
            port.apply(call); port.state['bedroom_ac.power'] = 'on'
            return {'final_status': 'SUCCESS', 'verification_result': True}
        for callback in (side_effect, lambda *_: {'final_status': 'SUBMITTED', 'verification_result': True}):
            with self.subTest(callback=callback.__name__):
                result, _, _ = self.run_case(f, p, t, on_call=callback)
                self.assertNotEqual(result.receipt['status'], 'SIMULATION_VERIFIED'); self.assertIsNone(result.evidence)

    def test_cancelled_policy_and_native_port_rejected_without_observation(self):
        f, p, t = bundle()
        for change, native in (({'cancelled': True}, False), ({}, True)):
            with self.subTest(change=change, native=native):
                result, port, _ = self.run_case(f, p, t, policy_change=change, native=native)
                self.assertEqual(port.calls, []); self.assertEqual(port.observations, [])
                self.assertNotEqual(result.receipt['status'], 'SIMULATION_VERIFIED')

    def test_changed_task_invalid_parameter_rejected_before_any_port_access(self):
        f, p, t = bundle(80); clock = support.Clock(); port = support.RoomPort(clock)
        with tempfile.TemporaryDirectory(prefix='p33-invalid-') as directory:
            store = flow_store.FlowStore.create(directory)
            try:
                draft = store.save_draft(canonical(f), p, 0); key = draft['key']
                store.check(key, 1, t, None); t['inputs']['value'] = 101
                result = run_logic_validation(store, key, t, records.ValidationAuthority(key, 'fixture.operator', True),
                                              lambda: (_ for _ in ()).throw(AssertionError('no policy before compile')), port, clock=clock)
                self.assertEqual(result.receipt['status'], 'REJECTED')
                self.assertEqual(port.calls, []); self.assertEqual(port.observations, [])
            finally: store.close()

    def test_run_does_not_publish_or_promote_store(self):
        f, p, t = bundle(80); clock = support.Clock(); port = support.RoomPort(clock)
        with tempfile.TemporaryDirectory(prefix='p33-readonly-store-') as directory:
            store = flow_store.FlowStore.create(directory)
            try:
                draft = store.save_draft(canonical(f), p, 0); key = draft['key']
                store.check(key, 1, t, None); before = store.load(key)
                plan = compiler.compile_flow(f, p, t, None)
                result = run_logic_validation(store, key, t, records.ValidationAuthority(key, 'fixture.operator', True),
                                              lambda: support.policy_for(plan), port, clock=clock)
                self.assertEqual(result.receipt['status'], 'SIMULATION_VERIFIED')
                self.assertEqual(store.load(key), before)
            finally: store.close()

    def test_derived_matrix_three_skills_three_repetitions_from_frozen_initial(self):
        for skill, value in (('SetBrightness', 60), ('SetTemperature', 22), ('SetPower', 'on')):
            f, p, t = bundle(value, skill)
            matrix = build_validation_plan(f, p, t)
            positives = [c for c in matrix['cases'] if c['category'] in (
                'DEMONSTRATION', 'UNSEEN_LEGAL', 'DIFFERENT_INITIAL', 'ALREADY_SATISFIED')]
            for case in positives:
                for repeat in range(3):
                    with self.subTest(skill=skill, category=case['category'], case=case['case_id'], repeat=repeat):
                        task = copy.deepcopy(t); task['inputs'] = case['task_inputs']
                        result, port, plan = self.run_case(f, p, task, case['frozen_initial_state'])
                        self.assertEqual(result.receipt['status'], 'SIMULATION_VERIFIED')
                        self.assertEqual(result.evidence.to_dict()['initial_state'], case['frozen_initial_state'])
                        events = []
                        for dispatched in port.calls:
                            call = dispatched['call']; cap = compiler.old.CAPS[call['skill']]
                            events.append({'step_id': 'set_value', 'target_key': call['args']['device'] + '.' + cap['property'],
                                           'value': call['args'][cap['argument']], 'submitted': True, 'effective': True})
                        score = score_execution(plan, result.receipt, case['frozen_initial_state'], port.state, events)
                        self.assertEqual(score['status'], 'LOGIC_ORACLE_CONFIRMED')
                        self.assertFalse(score['false_success']); self.assertFalse(score['wrong_action'])


class ScorerTests(unittest.TestCase):
    def setup_score(self, value=80):
        f, p, t = bundle(value); plan = compiler.compile_flow(f, p, t, None)
        initial = dict(support.STATE); final = dict(initial, **{'bedroom_light.brightnessPercent': value})
        events = [{'step_id': 'set_value', 'target_key': 'bedroom_light.brightnessPercent', 'value': value,
                   'submitted': True, 'effective': True}]
        return plan, initial, final, events

    def test_independent_effective_value_and_events_required(self):
        plan, initial, final, events = self.setup_score()
        out = score_execution(plan, {'status': 'SIMULATION_VERIFIED'}, initial, final, events)
        self.assertEqual(out['status'], 'LOGIC_ORACLE_CONFIRMED')
        self.assertFalse(out['device_execution_verified'])

    def test_false_success_and_wrong_action_are_separate(self):
        plan, initial, final, events = self.setup_score()
        out = score_execution(plan, {'status': 'SUCCESS'}, initial, initial, events)
        self.assertTrue(out['false_success']); self.assertFalse(out['wrong_action'])
        changed = dict(final, **{'bedroom_ac.power': 'on'})
        out = score_execution(plan, {'status': 'SUCCESS'}, initial, changed, events)
        self.assertTrue(out['false_success']); self.assertTrue(out['wrong_action'])

    def test_ack_submission_and_unknown_truth_cannot_pass(self):
        plan, initial, final, events = self.setup_score()
        for field in ('submitted', 'effective'):
            with self.subTest(field=field):
                bad = copy.deepcopy(events); bad[0][field] = False
                self.assertEqual(score_execution(plan, {'status': 'SUCCESS'}, initial, final, bad)['status'], 'FAILED')
        out = score_execution(plan, {'status': 'SUCCESS'}, initial, None, [])
        self.assertEqual(out['status'], 'UNCONFIRMED'); self.assertTrue(out['unsupported_success_claim'])
        self.assertIsNone(out['false_success'])

    def test_ABA_final_equality_cannot_hide_missing_intermediate_order(self):
        f, p, t = bundle(20)
        middle = copy.deepcopy(f['steps'][0]); middle['id'] = 'middle'; middle['argument'] = {'kind': 'literal', 'value': 80}
        f['steps'].insert(0, middle)
        plan = compiler.compile_flow(f, p, t, None); initial = dict(support.STATE)
        out = score_execution(plan, {'status': 'SUCCESS'}, initial, initial, [])
        self.assertEqual(out['status'], 'FAILED'); self.assertTrue(out['false_success'])
        events = [{'step_id': 'middle', 'target_key': 'bedroom_light.brightnessPercent', 'value': 80,
                   'submitted': True, 'effective': True},
                  {'step_id': 'set_value', 'target_key': 'bedroom_light.brightnessPercent', 'value': 20,
                   'submitted': True, 'effective': True}]
        self.assertEqual(score_execution(plan, {'status': 'SUCCESS'}, initial, initial, events)['status'], 'LOGIC_ORACLE_CONFIRMED')
        self.assertEqual(score_execution(plan, {'status': 'SUCCESS'}, initial, initial, list(reversed(events)))['status'], 'FAILED')

    def test_extra_event_or_wrong_type_or_missing_property_cannot_pass(self):
        plan, initial, final, events = self.setup_score()
        extra = events + [dict(events[0])]
        self.assertEqual(score_execution(plan, {'status': 'SUCCESS'}, initial, final, extra)['status'], 'FAILED')
        bad_final = dict(final); bad_final.pop('bedroom_ac.power')
        self.assertEqual(score_execution(plan, {'status': 'SUCCESS'}, initial, bad_final, events)['status'], 'UNCONFIRMED')
        bad_final = dict(final, **{'bedroom_light.brightnessPercent': True})
        self.assertNotEqual(score_execution(plan, {'status': 'SUCCESS'}, initial, bad_final, events)['status'], 'LOGIC_ORACLE_CONFIRMED')

    def test_unverified_intermediate_assert_and_blocking_unknown_never_pass(self):
        f, p, t = bundle(80)
        f['steps'].insert(0, {'id': 'assert_initial', 'op': 'assert', 'predicate': {
            'op': 'equals', 'left': {'kind': 'state', 'entity_input': 'entity', 'property': 'brightnessPercent'},
            'right': {'kind': 'literal', 'value': 70}}})
        plan = compiler.compile_flow(f, p, t, None)
        _, initial, final, events = self.setup_score()
        self.assertNotEqual(score_execution(plan, {'status': 'SUCCESS'}, initial, final, events)['status'], 'LOGIC_ORACLE_CONFIRMED')
        f, p, t = bundle(80)
        f['unknowns'] = [{'id': 'unknown.control', 'description': 'not located', 'impact': 'BLOCKS_EXECUTION'}]
        plan = compiler.compile_flow(f, p, t, None)
        self.assertEqual(score_execution(plan, {'status': 'SUCCESS'}, initial, final, events)['status'], 'UNCONFIRMED')


if __name__ == '__main__': unittest.main()
