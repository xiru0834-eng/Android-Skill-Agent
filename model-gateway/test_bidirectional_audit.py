import copy
import unittest
from bidirectional_audit import score, summarize


class TransferAuditTests(unittest.TestCase):
    def row(self):
        return dict(case_id='c1',arm='P-E',positive=True,expected={'light.brightnessPercent':80},
                    initial_state={'light.brightnessPercent':20,'ac.power':'off'},
                    final_observed_state={'light.brightnessPercent':80,'ac.power':'off'},
                    oracle={'light.brightnessPercent':80,'ac.power':'off'},
                    final_status='SUCCESS',model_correct=True,verification_result=True,
                    execution_actions=[{'property':'light.brightnessPercent','value':80}],
                    actual_actions=[{'property':'light.brightnessPercent','value':80}],
                    manual_adaptation={'redemonstrations':0,'skill_modifications':0,'binding_modifications':0},
                    evidence_complete=True,frozen=True,latency={'total_ms':100})

    def test_correct(self):self.assertTrue(score(self.row())['correct'])
    def test_wrong_value_is_false_success(self):
        r=self.row();r['oracle']['light.brightnessPercent']=60
        self.assertTrue(score(r)['false_success']);self.assertFalse(score(r)['correct'])
    def test_wrong_object_is_separately_counted(self):
        r=self.row();r['actual_actions']=[{'property':'ac.power','value':'on'}]
        self.assertTrue(score(r)['wrong_action'])
    def test_missing_final_evidence_is_not_success(self):
        r=self.row();r['oracle']={};self.assertTrue(score(r)['false_success'])
    def test_incomplete_journal_is_not_pass(self):
        r=self.row();r['evidence_complete']=False;self.assertFalse(score(r)['correct'])
    def test_assisted_not_zero_shot(self):
        r=self.row();r['manual_adaptation']['binding_modifications']=1
        self.assertTrue(score(r)['correct']);self.assertFalse(score(r)['zero_shot'])
    def test_drift_blocks_acceptance(self):
        r=self.row();r['frozen']=False;self.assertFalse(score(r)['correct'])
    def test_noop_with_input_is_not_pass(self):
        r=self.row();r['final_status']='NO_ACTION_REQUIRED';self.assertFalse(score(r)['correct'])
    def test_noop_checks_initial_and_final(self):
        r=self.row();r['final_status']='NO_ACTION_REQUIRED';r['execution_actions']=[];r['actual_actions']=[]
        self.assertFalse(score(r)['correct']);r['initial_state']['light.brightnessPercent']=80
        self.assertTrue(score(r)['correct'])
    def test_preserve_unmentioned_fields(self):
        r=self.row();r['oracle']['ac.power']='on';self.assertTrue(score(r)['wrong_action'])
    def test_unconfirmed_is_not_success_even_if_achieved(self):
        r=self.row();r['final_status']='UNCONFIRMED';self.assertFalse(score(r)['correct'])
    def test_model_error_is_e2e_failure(self):
        r=self.row();r['model_correct']=False;self.assertFalse(score(r)['correct'])
    def test_missing_cases_keeps_planned_denominator(self):
        s=summarize([self.row()],{'P-E':2});self.assertEqual(s['arms']['P-E']['rate'],.5)
        self.assertFalse(s['passed'])
    def test_duplicate_identity_refused(self):
        with self.assertRaises(ValueError):summarize([self.row(),self.row()],{'P-E':2})
    def test_challenges_not_in_success_denominator(self):
        r=self.row();r['case_id']='n';r['positive']=False;r['final_status']='REJECTED'
        r['expected']={};r['actual_actions']=[];r['execution_actions']=[];r['oracle']=r['initial_state']
        s=summarize([self.row(),r],{'P-E':1});self.assertEqual(s['arms']['P-E']['rate'],1)
    def test_wrong_value_even_on_correct_control(self):
        r=self.row();r['allowed_actions']=[{'property':'light.brightnessPercent','value':80}]
        r['actual_actions'][0]['value']=60;self.assertTrue(score(r)['wrong_action'])
    def test_order_cannot_be_reversed(self):
        r=self.row();r['allowed_actions']=[{'property':'light.brightnessPercent','value':60},{'property':'light.brightnessPercent','value':80}]
        self.assertTrue(score(r)['wrong_action'])

    def test_success_requires_verifier_and_all_actions(self):
        r=self.row();r['verification_result']=False
        self.assertFalse(score(r)['correct'])
        r=self.row();r['allowed_actions']=r['actual_actions']+[{ 'property':'light.brightnessPercent','value':80}]
        self.assertFalse(score(r)['correct'])

    def test_missing_challenges_blocks_final_gate(self):
        rows=[]
        for arm in ('P-P','E-E','P-E','E-P'):
            r=self.row();r['arm']=arm;rows.append(r)
        result=summarize(rows,{arm:1 for arm in ('P-P','E-E','P-E','E-P')},planned_challenges=1)
        self.assertFalse(result['passed'])


if __name__=='__main__':unittest.main()
