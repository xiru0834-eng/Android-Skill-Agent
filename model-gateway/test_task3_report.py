"""Independent intervention evidence, not a copy of the capture score."""
import unittest
import json
import tempfile
from pathlib import Path
from task3_report import intervention_proven,build


class ReportTests(unittest.TestCase):
    def test_incomplete_batches_keep_all_slots_and_proven_capture_block(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);normal=base/'normal';faults=base/'faults';normal.mkdir();faults.mkdir()
            failed=base/'failed-trace.json';failed.write_text(json.dumps(dict(end='REJECTED',error='NO_CONFIRMED_CHANGE')))
            for root in [normal,faults]:(root/'source-stability.json').write_text(json.dumps(dict(sourceStable=True)))
            (normal/'rows.json').write_text(json.dumps([dict(id='S6-i0-r0',status='BLOCKED',evidenceQualified=False,reason='S6_SOURCE_SAVE_AMBIGUOUS_WITHOUT_STATE_CHANGE',sourceFailure=str(failed))]))
            (faults/'rows.json').write_text('[]');build(normal,faults,base/'out')
            value=json.loads((base/'out/summary.json').read_text())
            self.assertEqual(sum(g['planned'] for g in value['groups'].values()),168)
            self.assertEqual(value['groups']['single']['BLOCKED'],1)
            self.assertEqual(value['groups']['single']['NOT_RUN'],53)
            self.assertEqual(value['verdict'],'NOT_READY')

    def test_capture_pass_without_raw_case_is_rejected_not_copied(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);normal=base/'normal';faults=base/'faults';normal.mkdir();faults.mkdir()
            for root in [normal,faults]:(root/'source-stability.json').write_text(json.dumps(dict(sourceStable=True)))
            (normal/'rows.json').write_text(json.dumps([dict(id='S1-i0-r0',status='PASS',evidenceQualified=True)]));(faults/'rows.json').write_text('[]')
            with self.assertRaisesRegex(ValueError,'CAPTURE_CLAIM_WITHOUT_RAW_CASE'):build(normal,faults,base/'out')

    def test_foreground_needs_same_running_case_real_input_and_launcher(self):
        before=dict(result=dict(status='RUNNING',runId='run'),oracle=dict(caseId='case',events=[dict(kind='input:wfOpenLamp')]))
        proof=dict(kind='normal-system-Home',resumed=['topResumedActivity=com.google.android.apps.nexuslauncher/.NexusLauncherActivity'])
        self.assertTrue(intervention_proven('foreground',before,proof,[],dict(runId='run'),'case'))
        for bad in [{**before,'result':dict(status='SUCCEEDED',runId='run')},{**before,'oracle':dict(caseId='case',events=[])},{**before,'oracle':dict(caseId='other',events=[dict(kind='input:wfOpenLamp')])}]:
            self.assertFalse(intervention_proven('foreground',bad,proof,[],dict(runId='run'),'case'))
        self.assertFalse(intervention_proven('foreground',before,proof,[],dict(runId='other'),'case'))

    def test_cancel_requires_unique_enabled_visible_stop_control(self):
        before=dict(result=dict(status='RUNNING',runId='run'),oracle=dict(caseId='case',events=[dict(kind='edit:wfLampValue20')]))
        proof=dict(kind='normal-overlay-Stop',bounds=[0,100,100,150])
        node={'resource-id':'edu.sydney.probe:id/teachOverlayFinish','text':'Stop / return','enabled':'true','bounds':'[0,100][100,150]'}
        self.assertTrue(intervention_proven('cancel',before,proof,[node],dict(runId='run'),'case'))
        for nodes in [[],[node,node],[{**node,'enabled':'false'}],[{**node,'bounds':'[0,100][100,100]'}]]:
            self.assertFalse(intervention_proven('cancel',before,proof,nodes,dict(runId='run'),'case'))


if __name__=='__main__':unittest.main()
