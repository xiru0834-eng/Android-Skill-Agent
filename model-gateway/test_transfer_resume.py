import unittest
from unittest.mock import patch
from pathlib import Path
from transfer_resume import resume_boundary,checked_diagnosis


class ResumeTests(unittest.TestCase):
    def test_matching_stopped_diagnosis(self):
        with patch.object(Path,'read_text',side_effect=['{"caseId":"a"}','{"status":"UNCONFIRMED"}']):
            checked_diagnosis(Path('diagnosis'),dict(caseId='a'))
    def test_wrong_case_diagnosis_rejected(self):
        with patch.object(Path,'read_text',side_effect=['{"caseId":"b"}','{"status":"UNCONFIRMED"}']):
            self.assertRaises(ValueError,checked_diagnosis,Path('diagnosis'),dict(caseId='a'))
    def test_running_diagnosis_rejected(self):
        with patch.object(Path,'read_text',side_effect=['{"caseId":"a"}','{"status":"RUNNING"}']):
            self.assertRaises(ValueError,checked_diagnosis,Path('diagnosis'),dict(caseId='a'))
    def test_can_continue_after_recorded_infra_failure(self):
        cases=[dict(i=i) for i in range(3)]
        rows=[dict(case=cases[0],confirmed_success=True),dict(case=cases[1],infrastructureFailure='start failed')]
        self.assertEqual(resume_boundary(cases,rows),2)
    def test_does_not_retry_failed_case(self):
        c=[dict(i=0),dict(i=1)];self.assertEqual(resume_boundary(c,[dict(case=c[0],infrastructureFailure='x')]),1)
    def test_reordered_or_missing_case_rejected(self):
        c=[dict(i=0),dict(i=1)]
        self.assertRaises(ValueError,resume_boundary,c,[dict(case=c[1],infrastructureFailure='x')])
    def test_running_or_complete_batch_rejected(self):
        c=[dict(i=0),dict(i=1)]
        self.assertRaises(ValueError,resume_boundary,c,[])
        self.assertRaises(ValueError,resume_boundary,c,[dict(case=c[0],confirmed_success=True)])
        self.assertRaises(ValueError,resume_boundary,c,[dict(case=v,infrastructureFailure='x') for v in c])


if __name__=='__main__':unittest.main()
