"""Offline evidence reducer tests; no product, ADB or model execution."""
import copy
import unittest

from repair_r4_analysis import compare_plans, interval_union_ms, reduce_timing


class EvidenceReducerTest(unittest.TestCase):
    def test_only_identity_fields_ignored(self):
        a = dict(task_id='a', task_hash='h1', cancellation_token_ref='c1', steps=[{'value': 60}])
        b = dict(task_id='b', task_hash='h2', cancellation_token_ref='c2', steps=[{'value': 60}])
        self.assertEqual(compare_plans(a, b)['semantic_verdict'], 'EQUIVALENT')
        self.assertEqual(len(compare_plans(a, b)['identity_differences']), 3)

    def test_boolean_not_equal_integer(self):
        self.assertEqual(compare_plans({'value': True}, {'value': 1})['semantic_verdict'], 'DIFFERENT')

    def test_missing_not_equal_null(self):
        self.assertEqual(compare_plans({}, {'value': None})['semantic_verdict'], 'DIFFERENT')

    def test_nested_identity_not_ignored(self):
        self.assertEqual(compare_plans({'steps': [{'task_id': 'a'}]}, {'steps': [{'task_id': 'b'}]})['semantic_verdict'], 'DIFFERENT')

    def test_order_parameter_authority_preserved(self):
        a = {'authorization_ref': 'current', 'steps': [{'v': 1}, {'v': 2}], 'budget': 8000}
        for b in ({**a, 'authorization_ref': 'old'}, {**a, 'steps': list(reversed(a['steps']))}, {**a, 'budget': 8001}):
            self.assertEqual(compare_plans(a, b)['semantic_verdict'], 'DIFFERENT')

    def test_interval_union_no_nested_double_count(self):
        self.assertEqual(interval_union_ms([(0, 10_000_000), (1_000_000, 3_000_000), (8_000_000, 12_000_000)]), 12)

    def test_clip_spans_to_call(self):
        self.assertEqual(interval_union_ms([(0, 5_000_000), (8_000_000, 14_000_000)], (4_000_000, 10_000_000)), 3)

    def test_invalid_time_rejected(self):
        with self.assertRaises(ValueError):
            interval_union_ms([(5, 4)])

    def sample(self):
        return {'latency': {'runtime_ms': 2500, 'launch_wait_ms': 1000}, 'launch_timing': {'task_started_ms': 10000},
                'task_deadline_ms': 18000, 'final_status': 'SUCCESS',
                'timing': {'clock': 'elapsedRealtimeNanos', 'dropped': 0, 'spans': [
                    {'phase': 'CALL.s', 'start_ns': 11_000_000_000, 'end_ns': 12_000_000_000},
                    {'phase': 'FINAL', 'start_ns': 12_100_000_000, 'end_ns': 12_200_000_000}]},
                'execution_actions': [{'ms': 11500}], 'observations': []}

    def test_remaining_and_final(self):
        x = reduce_timing(self.sample())
        self.assertEqual(x['remaining_at_launch_wait_sample_ms'], 7000)
        self.assertEqual(x['remaining_before_first_input_ms'], 6500)
        self.assertEqual(x['remaining_before_flow_final_ms'], 5900)
        self.assertEqual(x['completion_slack_ms'], 5500)

    def test_failed_final_not_reached_is_not_zero(self):
        a = self.sample(); a['timing']['spans'] = []; a['final_status'] = 'BUDGET_EXCEEDED'; a['latency']['runtime_ms'] = 8475
        x = reduce_timing(a)
        self.assertEqual(x['remaining_before_flow_final_ms'], 'NOT_REACHED')
        self.assertEqual(x['deadline_overrun_ms'], 475)
        self.assertIsNone(x['completion_slack_ms'])
        self.assertEqual(x['natural_complete_duration_ms'], 'NOT_MEASURED')

    def test_clock_domain_rejected(self):
        a = self.sample(); a['timing']['clock'] = 'uptimeMillis'
        with self.assertRaises(ValueError):
            reduce_timing(a)

    def test_missing_clock_data_does_not_invent_zero(self):
        a = self.sample(); del a['launch_timing']; a['execution_actions'] = []
        x = reduce_timing(a)
        self.assertEqual(x['remaining_before_first_input_ms'], 'NOT_REACHED')
        self.assertEqual(x['queue_ms'], 'NOT_MEASURED')

    def test_reduction_does_not_mutate_evidence(self):
        a = self.sample(); old = copy.deepcopy(a); reduce_timing(a)
        self.assertEqual(a, old)


if __name__ == '__main__':
    unittest.main()
