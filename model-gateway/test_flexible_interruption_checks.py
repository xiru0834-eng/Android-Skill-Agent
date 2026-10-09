import copy
import unittest
from flexible_interruption_checks import assess_kill,leave_passed, recording_passed, stop_passed

class InterruptionScoreTests(unittest.TestCase):
    def setUp(self):
        self.before=dict(runId='same',status='RUNNING',reason='STARTING')
        self.after=dict(runId='same',status='UNCONFIRMED',reason='SERVICE_RECONNECTED',finishedMs=2,
                        recovery=dict(noAutomaticResume=True,scope='LAST_PERSISTED_CHECKPOINT_ONLY'))
        self.oracle=dict(caseId='case1',events=[dict(kind='input:wfOpenLamp',ms=1)])
    def judge(self,after=None,latest=None,unchanged=True,archived=True):
        return assess_kill(self.before,after or self.after,self.oracle,self.oracle,latest or self.oracle,unchanged,archived)
    def test_sealed_checkpoint_with_no_extra_input(self):self.assertTrue(self.judge()['assessmentPassed'])
    def test_stale_running_checkpoint_is_not_accepted(self):self.assertFalse(self.judge(after=self.before)['assessmentPassed'])
    def test_extra_input_after_stop_is_not_hidden(self):
        latest=copy.deepcopy(self.oracle);latest['events'].append(dict(kind='edit:wfLampValue60'))
        self.assertFalse(self.judge(latest=latest)['assessmentPassed'])
    def test_changed_case_is_not_accepted(self):
        latest=copy.deepcopy(self.oracle);latest['caseId']='other'
        self.assertFalse(self.judge(latest=latest)['assessmentPassed'])
    def test_changed_approval_or_missing_archive_is_not_accepted(self):
        self.assertFalse(self.judge(unchanged=False)['assessmentPassed'])
        self.assertFalse(self.judge(archived=False)['assessmentPassed'])
    def test_generic_unconfirmed_without_recovery_marker_is_not_enough(self):
        after=copy.deepcopy(self.after);after.pop('recovery')
        self.assertFalse(self.judge(after=after)['assessmentPassed'])
    def test_leave_requires_wrong_app_same_run_and_no_extra_inputs(self):
        after=dict(runId='same',status='UNCONFIRMED',reason='WRONG_APP',finishedMs=2)
        args=(self.before,after,self.oracle,self.oracle,self.oracle,True)
        self.assertTrue(leave_passed(*args))
        for key,value in [('runId','other'),('status','SUCCEEDED'),('reason','TIMEOUT')]:
            changed=dict(after,**{key:value})
            self.assertFalse(leave_passed(self.before,changed,self.oracle,self.oracle,self.oracle,True))
        latest=copy.deepcopy(self.oracle);latest['events'].append(dict(kind='input:save'))
        self.assertFalse(leave_passed(self.before,after,self.oracle,self.oracle,latest,True))
        self.assertFalse(leave_passed(self.before,after,self.oracle,self.oracle,self.oracle,False))

class RecordingInterruptionTests(unittest.TestCase):
    def setUp(self):
        self.before=dict(traceId='trace',end='RECORDING',source='AUTOMATED',steps=[1,2,3])
        self.after=dict(self.before,end='CANCELLED',error='')
        self.oracle=dict(caseId='fixture',events=[dict(kind='input:save',ms=1)])
    def check(self,after=None,**changes):
        flags=dict(unchanged=True,compiler_rejected=True,generate_blocked=True,archive_ok=True)
        flags.update(changes)
        return recording_passed('record-cancel',self.before,after or self.after,self.oracle,self.oracle,self.oracle,**flags)
    def test_cancel_blocks_complete_recording(self):self.assertTrue(self.check())
    def test_stopped_or_changed_trace_cannot_pass(self):
        self.assertFalse(self.check(dict(self.after,end='STOPPED')))
        self.assertFalse(self.check(dict(self.after,traceId='other')))
    def test_compiler_ui_and_approval_are_required(self):
        for key in ('unchanged','compiler_rejected','generate_blocked'):
            self.assertFalse(self.check(**{key:False}))
    def test_recording_leave_requires_explicit_reason(self):
        after=dict(self.before,end='REJECTED',error='LEFT_ALLOWED_APPS')
        args=('record-leave',self.before,after,self.oracle,self.oracle,self.oracle,True,True,True,True)
        self.assertTrue(recording_passed(*args))
        after['error']='';self.assertFalse(recording_passed(*args))
    def test_recording_kill_requires_archive(self):
        after=dict(self.before,end='INTERRUPTED',error='PROCESS_RESTARTED')
        args=('record-kill',self.before,after,self.oracle,self.oracle,self.oracle,True,True,True)
        self.assertTrue(recording_passed(*args,True));self.assertFalse(recording_passed(*args,False))
    def test_stopping_does_not_accept_success_or_another_run(self):
        before=dict(runId='run');after=dict(runId='run',status='CANCELLED',reason='USER_OR_SERVICE_STOP',finishedMs=2)
        args=(before,after,self.oracle,self.oracle,self.oracle,True)
        self.assertTrue(stop_passed(*args))
        after['status']='SUCCEEDED';self.assertFalse(stop_passed(*args))
    def test_additional_input_rejects_stop(self):
        before=dict(runId='run');after=dict(runId='run',status='CANCELLED',reason='USER_OR_SERVICE_STOP',finishedMs=2)
        latest=copy.deepcopy(self.oracle);latest['events'].append(dict(kind='input:extra'))
        self.assertFalse(stop_passed(before,after,self.oracle,self.oracle,latest,True))
    def test_late_input_before_first_post_stop_snapshot_is_not_missed(self):
        before=dict(runId='run');after=dict(runId='run',status='CANCELLED',reason='USER_OR_SERVICE_STOP',finishedMs=2)
        stopped=copy.deepcopy(self.oracle);stopped['events'].append(dict(kind='input:late',ms=3))
        self.assertFalse(stop_passed(before,after,self.oracle,stopped,stopped,True))

if __name__=='__main__':unittest.main()
