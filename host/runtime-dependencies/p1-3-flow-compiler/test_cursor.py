from dataclasses import replace
from copy import deepcopy
import unittest
from checks import materialize_call, ReadEvidence
from compiler import compile_flow, CompileError
from cursor import CheckCursor
from fixtures import bundle, original_bundle
from test_checks import policy_for, observation


class DynamicCallTests(unittest.TestCase):
    def test_G4_materialize_literal_and_equal_target_noop(self):
        plan = compile_flow(*bundle(), None)
        result = materialize_call(plan, 0, observation(plan, 'set_value'), policy_for(plan), 100)
        self.assertEqual(result['call']['args']['percent'], 80)
        self.assertFalse(result['skip_business_input'])
        state = {'bedroom_light.brightnessPercent': 80}
        result = materialize_call(plan, 0, observation(plan, 'set_value', state), policy_for(plan), 100)
        self.assertTrue(result['skip_business_input'])
        self.assertFalse(result['execution_authority'])

    def test_G4_read_evidence_not_initial_or_current(self):
        flow, package, task = bundle()
        flow['steps'].insert(0, dict(id='before', op='read', target=flow['allowed_effects'][0]))
        flow['steps'][1]['argument'] = {'kind': 'read', 'step_id': 'before'}
        plan = compile_flow(flow, package, task, None)
        before = observation(plan, 'before', {'bedroom_light.brightnessPercent': 20})
        current = observation(plan, 'set_value', {'bedroom_light.brightnessPercent': 80}, 2)
        result = materialize_call(plan, 1, current, policy_for(plan), 100,
                                  reads={'before': ReadEvidence('before', before)})
        self.assertEqual(result['call']['args']['percent'], 20)
        for reads in ({}, {'before': ReadEvidence('before', current)}):
            with self.subTest(reads=reads), self.assertRaises(CompileError) as caught:
                materialize_call(plan, 1, current, policy_for(plan), 100, reads=reads)
            self.assertEqual(caught.exception.code, 'DYNAMIC_VALUE_UNKNOWN')

    def test_G4_dynamic_entity_range_and_missing_current_blocks(self):
        flow, package, task = bundle('SetTemperature', 26)
        flow['inputs'].append(dict(name='source', type='entity', default_rule='REQUIRE_EXPLICIT',
                                   required_capabilities=['SetBrightness']))
        task['inputs']['source'] = {'entity_id': 'bedroom_light'}
        flow['dependencies']['capabilities'].append('SetBrightness')
        # Wrong units must be rejected statically, not converted to temperature.
        flow['steps'][0]['argument'] = dict(kind='state', entity_input='source', property='brightnessPercent')
        with self.assertRaises(CompileError) as caught:
            compile_flow(flow, package, task, None)
        self.assertEqual(caught.exception.code, 'TYPE_MISMATCH')
        plan = compile_flow(*bundle(), None)
        with self.assertRaises(CompileError) as caught:
            materialize_call(plan, 0, observation(plan, 'set_value', {'bedroom_light.power': 'on'}), policy_for(plan), 100)
        self.assertEqual(caught.exception.code, 'CURRENT_VALUE_UNKNOWN')

    def test_G5_dynamic_permission_recheck_and_stale_frame(self):
        plan = compile_flow(*bundle(), None)
        for context, frame, code in [(policy_for(plan, revoked=True), observation(plan, 'set_value'), 'PERMISSION_REVOKED'),
                                      (policy_for(plan), observation(plan, 'ENTRY'), 'OBSERVATION_UNAVAILABLE')]:
            with self.subTest(code=code), self.assertRaises(CompileError) as caught:
                materialize_call(plan, 0, frame, context, 100)
            self.assertEqual(caught.exception.code, code)


class CursorTests(unittest.TestCase):
    def plan(self, values=(20, 80, 20)):
        flow, package, task = bundle(value=values[-1])
        flow['steps'] = [dict(id='set_' + str(i), op='call', capability='SetBrightness', entity_input='entity',
                             argument={'kind': 'literal', 'value': value}) for i, value in enumerate(values)]
        return compile_flow(flow, package, task, None)

    def run_fixture(self, plan, fail_step=None, mutate_property=None):
        context = policy_for(plan)
        checker = CheckCursor(plan, lambda: context)
        frame = observation(plan, 'ENTRY')
        checker.start(frame, 100)
        state = __import__('json').loads(frame.values_json)
        inputs = []
        seq = 2
        for index, step in enumerate(plan.to_dict()['steps']):
            prepared = checker.prepare_next(observation(plan, step['id'], state, seq), 100)
            seq += 1
            if step['op'] == 'CALL':
                if not prepared['skip_business_input']:
                    inputs.append(deepcopy(prepared['call']))  # TEST_FIXTURE applied value, not Android action.
                if fail_step != index:
                    state[step['target_key']] = prepared['call']['args'][step['argument']]
                if mutate_property:
                    state[mutate_property] = 'on'
                checker.confirm_call(observation(plan, 'AFTER.' + step['id'], state, seq), 100)
                seq += 1
        return checker.finish(observation(plan, 'FINAL', state, seq), 100), inputs

    def test_G3_ABA_checked_stepwise_not_final_only(self):
        result, inputs = self.run_fixture(self.plan())
        self.assertEqual([c['args']['percent'] for c in inputs], [80, 20])
        self.assertEqual(result['completed_calls'], 3)
        self.assertEqual(result['status'], 'CHECK_SEQUENCE_VERIFIED')
        self.assertFalse(result['device_execution_verified'])

    def test_G3_cannot_skip_to_finish_or_skip_confirmation(self):
        plan = self.plan()
        checker = CheckCursor(plan, lambda: policy_for(plan))
        checker.start(observation(plan, 'ENTRY'), 100)
        with self.assertRaises(CompileError) as caught:
            checker.finish(observation(plan, 'FINAL', sequence=2), 100)
        self.assertEqual(caught.exception.code, 'FLOW_INCOMPLETE')
        checker = CheckCursor(plan, lambda: policy_for(plan))
        checker.start(observation(plan, 'ENTRY'), 100)
        checker.prepare_next(observation(plan, 'set_0', sequence=2), 100)
        with self.assertRaises(CompileError) as caught:
            checker.prepare_next(observation(plan, 'set_1', sequence=3), 100)
        self.assertEqual(caught.exception.code, 'STEP_CONFIRMATION_REQUIRED')

    def test_G4_false_or_unknown_precondition_stops_without_task_data(self):
        flow, package, task = bundle()
        flow['preconditions'] = [deepcopy(flow['goals'][0])]
        plan = compile_flow(flow, package, task, None)
        for state, code in [({'bedroom_light.brightnessPercent': 20}, 'PRECONDITION_FALSE'),
                              ({'bedroom_light.power': 'off'}, 'PRECONDITION_UNKNOWN')]:
            with self.subTest(code=code):
                checker = CheckCursor(plan, lambda: policy_for(plan))
                with self.assertRaises(CompileError) as caught:
                    checker.start(observation(plan, 'ENTRY', state), 100)
                self.assertEqual(caught.exception.code, code)
                with self.assertRaises(CompileError):
                    checker.prepare_next(observation(plan, 'set_value', sequence=2), 100)

    def test_G4_read_assert_current_value_vs_task_initial(self):
        flow, package, task = original_bundle()
        flow['unknowns'] = []  # TEST_FIXTURE read provider, not native implementation.
        plan = compile_flow(flow, package, task, None)
        result, inputs = self.run_fixture(plan)
        self.assertEqual(result['completed_steps'], 4)
        self.assertEqual(len(inputs), 1)

    def test_G4_action_not_effective_and_wrong_entity_fail(self):
        with self.assertRaises(CompileError) as caught:
            self.run_fixture(self.plan((80,)), fail_step=0)
        self.assertEqual(caught.exception.code, 'VERIFICATION_ERROR')
        with self.assertRaises(CompileError) as caught:
            self.run_fixture(self.plan((80,)), mutate_property='bedroom_ac.power')
        self.assertEqual(caught.exception.code, 'FORBIDDEN_SIDE_EFFECT')

    def test_G5_cancel_or_timeout_midflow_no_more_data(self):
        plan = self.plan()
        current_policy = policy_for(plan)
        checker = CheckCursor(plan, lambda: current_policy)
        checker.start(observation(plan, 'ENTRY'), 100)
        prepared = checker.prepare_next(observation(plan, 'set_0', sequence=2), 100)
        self.assertTrue(prepared['skip_business_input'])
        current_policy = replace(current_policy, cancelled=True)
        with self.assertRaises(CompileError) as caught:
            checker.confirm_call(observation(plan, 'AFTER.set_0', sequence=3), 100)
        self.assertEqual(caught.exception.code, 'CANCELLED')
        with self.assertRaises(CompileError) as caught:
            checker.prepare_next(observation(plan, 'set_1', sequence=4), 100)
        self.assertEqual(caught.exception.code, 'SESSION_STOPPED')

    def test_G7_partial_sequence_is_not_success(self):
        plan = self.plan((80, 20))
        checker = CheckCursor(plan, lambda: policy_for(plan))
        checker.start(observation(plan, 'ENTRY'), 100)
        checker.prepare_next(observation(plan, 'set_0', sequence=2), 100)
        state = {'bedroom_light.power': 'off', 'bedroom_light.brightnessPercent': 80,
                 'bedroom_ac.power': 'off', 'bedroom_ac.temperatureCelsius': 22}
        checker.confirm_call(observation(plan, 'AFTER.set_0', state, 3), 100)
        checker.prepare_next(observation(plan, 'set_1', state, 4), 100)
        with self.assertRaises(CompileError):
            checker.confirm_call(observation(plan, 'AFTER.set_1', state, 5), 100)
        self.assertEqual(checker.receipt()['completed_calls'], 1)
        self.assertEqual(checker.receipt()['status'], 'CHECK_SEQUENCE_STOPPED')

    def test_G4_initial_reference_in_precondition(self):
        flow, package, task = bundle()
        predicate = deepcopy(flow['goals'][0])
        predicate['right'] = dict(kind='initial', entity_input='entity', property='brightnessPercent')
        flow['preconditions'] = [predicate]
        plan = compile_flow(flow, package, task, None)
        checker = CheckCursor(plan, lambda: policy_for(plan))
        self.assertEqual(checker.start(observation(plan, 'ENTRY'), 100)['status'], 'CHECK_SEQUENCE_PENDING')

    def test_G6_budget_cannot_reset_between_steps(self):
        plan = self.plan()
        context = policy_for(plan)
        checker = CheckCursor(plan, lambda: context)
        checker.start(observation(plan, 'ENTRY'), 100)
        context = replace(context, started_ms=100, deadline_ms=8100)
        with self.assertRaises(CompileError) as caught:
            checker.prepare_next(observation(plan, 'set_0', sequence=2), 100)
        self.assertEqual(caught.exception.code, 'BUDGET_CONTEXT_CHANGED')

    def test_G6_clock_backwards_and_provider_failure_stops(self):
        plan = self.plan()
        checker = CheckCursor(plan, lambda: policy_for(plan))
        checker.start(observation(plan, 'ENTRY'), 150)
        with self.assertRaises(CompileError) as caught:
            checker.prepare_next(observation(plan, 'set_0', sequence=2), 100)
        self.assertEqual(caught.exception.code, 'CLOCK_ERROR')
        state = {'fail': False}
        def provider():
            if state['fail']:
                raise RuntimeError('TEST_FIXTURE provider unavailable')
            return policy_for(plan)
        checker = CheckCursor(plan, provider)
        checker.start(observation(plan, 'ENTRY'), 100)
        state['fail'] = True
        with self.assertRaises(CompileError) as caught:
            checker.prepare_next(observation(plan, 'set_0', sequence=2), 100)
        self.assertEqual(caught.exception.code, 'POLICY_CONTEXT_UNAVAILABLE')
        self.assertEqual(checker.receipt()['status'], 'CHECK_SEQUENCE_STOPPED')

    def test_G4_observation_from_other_execution_session_rejected(self):
        plan = self.plan()
        checker = CheckCursor(plan, lambda: policy_for(plan))
        checker.start(observation(plan, 'ENTRY'), 100)
        current = observation(plan, 'set_0', sequence=2)
        # Simulate a current-looking response from a different observation lease.
        object.__setattr__(current, 'observation_session_id', 'observe.other_session')
        with self.assertRaises(CompileError) as caught:
            checker.prepare_next(current, 100)
        self.assertEqual(caught.exception.code, 'OBSERVATION_UNAVAILABLE')


if __name__ == '__main__':
    unittest.main()
