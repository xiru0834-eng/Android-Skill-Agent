import unittest
from recovery_matrix import blocks, source_closure
from pathlib import Path


class RecoveryMatrixTest(unittest.TestCase):
    def test_confirmation_has_balanced_cases_and_repeats(self):
        schedule=blocks('confirmation');self.assertEqual(sum(len(b['cases']) for b in schedule),48)
        self.assertEqual([b['policy'] for b in schedule],['OFF','R1','R1','OFF','OFF','R1'])
        for i in range(0,6,2):self.assertEqual(schedule[i]['cases'],schedule[i+1]['cases'])
        self.assertEqual(schedule,blocks('confirmation'))

    def test_display_is_fixed_skill_not_new_independent_skills(self):
        schedule=blocks('display');self.assertEqual(len(schedule),12)
        self.assertEqual(sum(len(b['cases']) for b in schedule),24)
        self.assertEqual({b['config'] for b in schedule},{'reference','same-dp','compact','wide'})

    def test_frozen_harness_contains_transitive_local_imports(self):
        names=source_closure(Path(__file__).parent,['recovery_matrix.py','recovery_audit.py'])
        for name in ['transfer_cases.py','transfer_requests.py','workflow_score.py','transfer_input_ready.py']:
            self.assertIn(name,names)

    def test_revised_candidate_is_a_separate_development_batch(self):
        schedule=blocks('r2-development');cases=schedule[0]['cases']
        self.assertEqual(len(cases),15)
        self.assertEqual(sum(c['fault']=='transient_save' for c in cases),10)
        self.assertEqual(schedule[0]['policy'],'R2')
        self.assertEqual({b['policy'] for b in blocks('display-r2')},{'R2'})

    def test_profile_schedules_are_prespecified(self):
        from collections import Counter
        smoke=blocks('profile-smoke')
        self.assertEqual([c['condition'] for c in smoke[0]['cases']],['S0','S5','transient_save'])
        phone=blocks('profile-phone');cases=[c for b in phone for c in b['cases']]
        self.assertEqual(len(cases),39)
        self.assertEqual(Counter(c['condition'] for c in cases),Counter({c:3 for c in
            ['S0','S1','S2','S3','S4','S5','missing','duplicate','rollback','dirty','drop','late_save','transient_save']}))
        self.assertEqual(phone,blocks('profile-phone'))
        display=blocks('profile-display')
        self.assertEqual(len([c for b in display for c in b['cases']]),12)
        self.assertEqual({b['config'] for b in display},{'reference','compact'})
        self.assertEqual({b['policy'] for b in phone+display+smoke},{'R2'})


if __name__=='__main__':unittest.main()
