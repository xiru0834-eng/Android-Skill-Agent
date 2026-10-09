import unittest
from profile_report import summarize_acceptance


class ProfileReportTest(unittest.TestCase):
    def row(self,condition,success,inputs=0):
        return dict(evidence_complete=True,case=dict(condition=condition),confirmed_success=success,
                    false_success=False,post_terminal_inputs=0,inputs=inputs,status='SUCCEEDED' if success else 'UNCONFIRMED')

    def test_failure_to_complete_not_a_safety_success(self):
        v=summarize_acceptance([self.row('S0',False)],3,aborted=False)
        self.assertEqual(v['positiveCompleted'],0)
        self.assertEqual(v['positiveAttempted'],1)
        self.assertEqual(v['unattempted'],2)
        self.assertFalse(v['complete'])

    def test_expected_stop_is_not_task_completion(self):
        v=summarize_acceptance([self.row('missing',False),self.row('transient_save',True)],2,aborted=False)
        self.assertEqual(v['negativeStopped'],1)
        self.assertEqual(v['positiveCompleted'],1)
        self.assertTrue(v['complete'])

    def test_preparation_abort_does_not_disappear(self):
        v=summarize_acceptance([],3,aborted=True)
        self.assertEqual(v['abortedBatches'],1)
        self.assertEqual(v['incompleteEvidenceCases'],0)
        self.assertEqual(v['unattempted'],3)

    def test_fault_without_expected_stop_is_not_pass(self):
        v=summarize_acceptance([self.row('missing',True),self.row('dirty',False,1)],2,aborted=False)
        self.assertEqual(v['negativeStopped'],1)
        self.assertEqual(v['zeroInputViolations'],1)

    def test_missing_evidence_never_counted_complete(self):
        v=summarize_acceptance([dict(evidence_complete=False)],1,aborted=True)
        self.assertFalse(v['complete'])
        self.assertEqual(v['incompleteEvidenceCases'],1)

    def test_false_report_is_not_an_expected_stop(self):
        row=self.row('missing',False);row.update(status='SUCCEEDED',false_success=True)
        v=summarize_acceptance([row],1,aborted=False)
        self.assertEqual(v['negativeStopped'],0)
        self.assertEqual(v['falseSuccess'],1)


if __name__=='__main__':unittest.main()
