import copy
import unittest
from jev_deployment_smoke import verify_execution,verify_session


class DeploymentAuditTests(unittest.TestCase):
    def test_routed_deployment_requires_its_own_session_and_port(self):
        verify_session(dict(selector='routed',port=8767),'routed')
        verify_session(dict(selector='jev',port=8766),'jev')
        for session in [dict(selector='jev',port=8767),dict(selector='routed',port=8766)]:
            with self.assertRaises(AssertionError):verify_session(session,'routed')

    def base(self):
        return dict(actual_success=True, confirmed_success=True, false_success=False,
                    non_target_violation=False, post_terminal_inputs=0, route=dict(valid=True),
                    inputSafety=dict(afterDeadlineInputs=0, unexpectedIds=0, extraInputs=0))

    def test_complete_zero_input_violations_pass(self):
        verify_execution(self.base(), partial=False)

    def test_missing_metric_is_not_treated_as_zero(self):
        row = self.base()
        row['inputSafety'] = dict(unexpected=0, afterDeadline=0, postTerminal=0)
        with self.assertRaises(KeyError):
            verify_execution(row, partial=False)

    def test_each_long_workflow_input_violation_fails(self):
        for key in ('afterDeadlineInputs', 'unexpectedIds', 'extraInputs'):
            row = copy.deepcopy(self.base())
            row['inputSafety'][key] = 1
            with self.subTest(key=key), self.assertRaises(AssertionError):
                verify_execution(row, partial=False)

    def test_partial_workflow_checks_exact_counters(self):
        row = self.base()
        row.update(extraInputs=0, unexpectedInputs=0, afterDeadlineInputs=0)
        verify_execution(row, partial=True)
        del row['extraInputs']
        with self.assertRaises(KeyError):
            verify_execution(row, partial=True)


if __name__ == '__main__':
    unittest.main()
