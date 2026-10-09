import json
import tempfile
import unittest
from pathlib import Path
from recovery_evidence import diagnose, seal, verify, audit_route


class EvidenceTest(unittest.TestCase):
    def old_trace(self):
        result=dict(runId='one',status='UNCONFIRMED',reason='STEP_UNCONFIRMED',finishedMs=900,actions=[dict(id='wfLampSave')])
        journal=[dict(kind='START',runId='one',data=dict(steps=[dict(id='a'),dict(id='b'),dict(id='c'),dict(id='wfLampSave')])),
                 dict(kind='RESULT',runId='one',phase=2,stepIndex=3,data=dict(result))]
        return result,journal

    def test_old_result_locates_failure_from_its_terminal_journal(self):
        result,journal=self.old_trace();value=diagnose(result,journal)
        self.assertEqual(value['phase'],2);self.assertEqual(value['stepNumber'],4)
        self.assertEqual(value['targetId'],'wfLampSave')
        self.assertTrue(value['actionDispatchedAtFailedStep'])

    def test_old_result_does_not_borrow_another_runs_location(self):
        result,journal=self.old_trace();journal[-1]['runId']='other'
        self.assertIsNone(diagnose(result,journal)['stepNumber'])

    def test_modern_explicit_location_stays_authoritative(self):
        result,journal=self.old_trace();result.update(terminalPhase=3,terminalStepIndex=8,terminalStepId=None)
        value=diagnose(result,journal)
        self.assertEqual(value['phase'],3);self.assertIsNone(value['targetId']);self.assertIsNone(value['stepNumber'])

    def test_terminal_journal_must_match_the_actual_terminal_result(self):
        result,journal=self.old_trace();journal[-1]['data']['finishedMs']=800
        self.assertIsNone(diagnose(result,journal)['stepNumber'])

    def test_stale_state_node_is_observation_failure_not_unknown_or_input_failure(self):
        for phase in (1,2):
            result=dict(status='UNCONFIRMED',reason='STALE:wfReady',terminalPhase=phase,
                        terminalStepIndex=7,terminalStepId='wfFanSave',actions=[])
            value=diagnose(result,[])
            self.assertEqual(value['category'],'OBSERVATION')
            self.assertEqual(value['reason'],'STALE:wfReady')
            self.assertEqual(value['targetId'],'wfFanSave')
            self.assertFalse(value['recoveredTask'])
            self.assertEqual(value['causeCertainty'],'OBSERVED_SYMPTOM_ONLY')

    def test_locates_observed_failure_without_fault_label(self):
        result=dict(status='UNCONFIRMED',reason='MISSING:wfFanSave',terminalPhase=1,
                    terminalStepIndex=7,terminalStepId='wfFanSave',actions=[])
        value=diagnose(result,[])
        self.assertEqual(value['category'],'LOCATE')
        self.assertEqual(value['stepNumber'],8)
        self.assertFalse(value['actionDispatchedAtFailedStep'])
        self.assertEqual(value['causeCertainty'],'OBSERVED_SYMPTOM_ONLY')

    def test_recovery_is_not_claimed_without_terminal_success(self):
        journal=[dict(kind='RECOVERY_WAIT',data={}),dict(kind='RECOVERY_LOCATED',data={})]
        for status,expected in [('UNCONFIRMED',False),('SUCCEEDED',True)]:
            value=diagnose(dict(status=status,reason='FINAL_TARGET_MISMATCH',actions=[]),journal)
            self.assertEqual(value['recoveredTask'],expected)

    def test_input_ledger_marks_failed_step_already_dispatched(self):
        result=dict(status='UNCONFIRMED',reason='STEP_UNCONFIRMED',terminalPhase=2,
                    terminalStepIndex=3,terminalStepId='wfLampSave',actions=[dict(id='wfLampSave')])
        self.assertTrue(diagnose(result,[])['actionDispatchedAtFailedStep'])
        self.assertEqual(diagnose(result,[])['category'],'POST_ACTION_CONFIRMATION')

    def test_seal_is_relocatable_and_detects_all_file_changes(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'proof.json').write_text('{}');seal(root)
            self.assertTrue(verify(root)['valid'])
            (root/'proof.json').write_text('{"changed":true}')
            self.assertEqual(verify(root)['changed'],['proof.json'])
            (root/'proof.json').unlink()
            self.assertEqual(verify(root)['missing'],['proof.json'])
            (root/'extra.json').write_text('{}')
            self.assertEqual(verify(root)['unexpected'],['extra.json'])

    def test_manifest_rejects_escaping_paths(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'integrity.json').write_text(json.dumps({'files':{'../private':'0'}}))
            with self.assertRaises(ValueError):verify(root)

    def test_unknown_reason_is_not_invented_root_cause(self):
        self.assertEqual(diagnose(dict(status='UNCONFIRMED',reason='NEW',actions=[]),[])['category'],'UNKNOWN')

    def test_nested_manifest_named_file_is_still_covered(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'nested').mkdir();(root/'nested/integrity.json').write_text('{}')
            seal(root);(root/'nested/integrity.json').write_text('changed')
            self.assertEqual(verify(root)['changed'],['nested/integrity.json'])

    def test_action_route_allows_skips_but_not_reordering_or_repetition(self):
        skill={'steps':[{'id':'a','sourceIndex':1},{'id':'b','sourceIndex':2},{'id':'c','sourceIndex':3}]}
        a,b,c=skill['steps']
        self.assertTrue(audit_route({'actions':[a,c]},skill)['valid'])
        for actions in ([c,a],[a,a],[{'id':'x','sourceIndex':1}],[{'id':'a','sourceIndex':3}]):
            self.assertFalse(audit_route({'actions':actions},skill)['valid'])


if __name__=='__main__':unittest.main()
