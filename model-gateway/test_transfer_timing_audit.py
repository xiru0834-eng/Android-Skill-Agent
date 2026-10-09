import unittest
from transfer_timing_audit import inspect_timing


class TimingAuditTests(unittest.TestCase):
    def result(self,**changes):
        value=dict(startedMs=0,finishedMs=9000,deadlineMs=30000,status='SUCCEEDED',actions=[dict(ms=5000,id='a')])
        value.update(changes);return value
    def event(self,deadline=8000):
        return dict(kind='INPUT_RETURN',data=dict(dispatchedMs=5000,confirmationDeadlineMs=deadline))
    def test_correct_window(self):self.assertTrue(inspect_timing(self.result(),[self.event()])['passes'])
    def test_old_window_rejected(self):self.assertFalse(inspect_timing(self.result(),[self.event(3000)])['passes'])
    def test_late_success_rejected(self):self.assertFalse(inspect_timing(self.result(finishedMs=30000),[self.event()])['passes'])
    def test_timeout_not_mistaken_for_late_success(self):
        self.assertTrue(inspect_timing(self.result(finishedMs=31000,status='UNCONFIRMED'),[self.event()])['passes'])
    def test_action_after_deadline_rejected(self):
        self.assertFalse(inspect_timing(self.result(actions=[dict(ms=30001,id='a')]),[self.event()])['passes'])
    def test_missing_dispatch_evidence_rejected(self):self.assertFalse(inspect_timing(self.result(),[])['passes'])
    def test_no_action_valid(self):self.assertTrue(inspect_timing(self.result(actions=[]),[])['passes'])


if __name__=='__main__':unittest.main()
