from dataclasses import replace
import unittest
from compiler import compile_flow, CompileError
from dependencies import canonical, digest
from fixtures import bundle
from checks import PolicyContext, Observation, check_task_policy, evaluate_predicate

def policy_for(plan, **changes):
    data = plan.to_dict()
    defaults = dict(plan_hash=digest(data), host_device_id=data['host_device_id'],
                    environment_hash=data['environment_hash'], authorization_ref=data['authorization_ref'],
                    cancellation_token_ref=data['cancellation_token_ref'],
                    allowed_writes=frozenset(data['actual_write_set']), started_ms=0, deadline_ms=8000,
                    max_actions=32, local_approval_verified=True,
                    observation_session_id='observe.session_fixture',
                    approved_raw_package_hash='a2e33984878d8aec080d1fa69d605d9fc762dc2cbc2db3a0d89d8e65f7ec69a0')
    return PolicyContext(**dict(defaults, **changes))

def observation(plan, phase, state=None, sequence=1, captured_ms=100):
    data = plan.to_dict()
    state = state or {'bedroom_light.power': 'off', 'bedroom_light.brightnessPercent': 20,
                      'bedroom_ac.power': 'off', 'bedroom_ac.temperatureCelsius': 22}
    return Observation(data['task_id'], data['host_device_id'], data['environment_hash'], phase,
                       sequence, captured_ms, canonical(state), 'observe.session_fixture')

class PureCheckTests(unittest.TestCase):
    def setUp(self):
        self.plan = compile_flow(*bundle(), None)

    def rejection(self, context, code, now_ms=100):
        with self.assertRaises(CompileError) as caught:
            check_task_policy(self.plan, context, now_ms)
        self.assertEqual(caught.exception.code, code)

    def test_G5_missing_trusted_policy_cannot_self_approve(self):
        self.rejection(None, 'POLICY_CONTEXT_UNAVAILABLE')
        self.rejection({'approved': True}, 'POLICY_CONTEXT_UNAVAILABLE')

    def test_G5_policy_checked_but_not_click_authority(self):
        result = check_task_policy(self.plan, policy_for(self.plan), 100)
        self.assertEqual(result['permission_state'], 'CHECKED_TEST_FIXTURE')
        self.assertFalse(result['execution_authority'])
        self.assertEqual(result['deadline_ms'], 8000)

    def test_G5_scope_and_hash_restrictions(self):
        for changes, code in [({'allowed_writes': frozenset()}, 'PERMISSION_DENIED'),
                               ({'plan_hash': 'changed'}, 'POLICY_BINDING_MISMATCH'),
                               ({'host_device_id': 'other'}, 'POLICY_BINDING_MISMATCH'),
                               ({'environment_hash': 'old'}, 'POLICY_BINDING_MISMATCH'),
                               ({'authorization_ref': 'fake'}, 'POLICY_BINDING_MISMATCH'),
                               ({'cancellation_token_ref': 'fake'}, 'POLICY_BINDING_MISMATCH'),
                               ({'local_approval_verified': False}, 'LOCAL_REVIEW_REQUIRED'),
                               ({'approved_raw_package_hash': 'bad'}, 'LOCAL_REVIEW_REQUIRED'),
                               ({'cancelled': True}, 'CANCELLED'), ({'revoked': True}, 'PERMISSION_REVOKED')]:
            with self.subTest(changes=changes):
                self.rejection(policy_for(self.plan, **changes), code)

    def test_G6_whole_deadline_and_insufficient_resources(self):
        self.rejection(policy_for(self.plan), 'BUDGET_INSUFFICIENT', now_ms=8000)
        self.rejection(policy_for(self.plan, max_actions=0), 'BUDGET_INSUFFICIENT')
        self.rejection(policy_for(self.plan, deadline_ms=10000), 'BUDGET_LIMIT_EXCEEDED')
        self.rejection(policy_for(self.plan, estimated_required_ms=7901), 'BUDGET_INSUFFICIENT')
        context = policy_for(self.plan, deadline_ms=7000)
        self.assertEqual(check_task_policy(self.plan, context, 1000)['deadline_ms'], 7000)
        self.assertEqual(check_task_policy(self.plan, context, 6000)['deadline_ms'], 7000)

    def test_G6_task_budget_is_not_old_runtime_override(self):
        flow, package, task = bundle()
        task['budget']['duration_ms'] = 10000
        self.plan = compile_flow(flow, package, task, None)
        self.rejection(policy_for(self.plan), 'BUDGET_LIMIT_EXCEEDED')
        task['budget']['duration_ms'] = 8000
        task['budget']['max_actions'] = 0
        self.plan = compile_flow(flow, package, task, None)
        self.rejection(policy_for(self.plan), 'BUDGET_INSUFFICIENT')

    def test_G4_true_false_unknown_distinct(self):
        predicate = self.plan.to_dict()['goals'][0]
        for value, expected in [(80, 'TRUE'), (20, 'FALSE'), (None, 'UNKNOWN'), (80.0, 'UNKNOWN'), ('80', 'UNKNOWN')]:
            with self.subTest(value=value):
                frame = observation(self.plan, 'FINAL', {'bedroom_light.brightnessPercent': value})
                self.assertEqual(evaluate_predicate(self.plan, predicate, frame, 'FINAL', 100), expected)

    def test_G4_current_is_not_initial(self):
        predicate = self.plan.to_dict()['goals'][0]
        current = observation(self.plan, 'FINAL', {'bedroom_light.brightnessPercent': 80}, 2)
        initial = observation(self.plan, 'ENTRY', {'bedroom_light.brightnessPercent': 20})
        self.assertEqual(evaluate_predicate(self.plan, predicate, current, 'FINAL', 100, initial=initial), 'TRUE')
        same_initial = dict(predicate, right={'kind': 'initial', 'key': 'bedroom_light.brightnessPercent', 'type': 'integer', 'unit': 'percent'})
        self.assertEqual(evaluate_predicate(self.plan, same_initial, current, 'FINAL', 100, initial=initial), 'FALSE')

    def test_G4_wrong_phase_old_clock_host_env_and_sequence_unknown(self):
        good = observation(self.plan, 'FINAL', {'bedroom_light.brightnessPercent': 80}, 2)
        for frame in [replace(good, phase='ENTRY'), replace(good, host_device_id='other'),
                       replace(good, environment_hash='old'), replace(good, task_id='other'),
                       replace(good, captured_ms=101), replace(good, captured_ms=-1),
                       replace(good, sequence=0)]:
            with self.subTest(frame=frame):
                self.assertEqual(evaluate_predicate(self.plan, self.plan.to_dict()['goals'][0], frame,
                                                    'FINAL', 100, min_sequence=1), 'UNKNOWN')
        self.assertEqual(evaluate_predicate(self.plan, self.plan.to_dict()['goals'][0], good, 'FINAL', 601), 'UNKNOWN')


if __name__ == '__main__':
    unittest.main()
