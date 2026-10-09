import unittest
from workflow_experiment import cases

class CasesTests(unittest.TestCase):
    def test_normal_matrix_has_paired_policies(self):
        rows=cases('normal',2)
        self.assertEqual(len(rows),96)
        for row in rows[::2]:
            peer=next(x for x in rows if x['pair']==row['pair'] and x['policy']!=row['policy'])
            self.assertEqual(row['initial'],peer['initial']);self.assertEqual(row['goal'],peer['goal'])
    def test_low_goal_preserves_two_fields(self):
        for row in cases('normal',1):
            self.assertEqual(sum(v is not None for v in row['goal']),row['load'])
    def test_challenges_have_expected_outcomes(self):
        rows=cases('challenge',1)
        self.assertEqual(len(rows),32)
        self.assertTrue(any(r['expect']=='CANCELLED' for r in rows))

if __name__=='__main__':unittest.main()
