import unittest
from collections import Counter
from reliability_existing import schedule


class ExistingReliabilityTest(unittest.TestCase):
    def test_normal_is_six_initial_states_repeated_three_times(self):
        blocks=schedule('normal');cases=blocks[0]['cases']
        self.assertEqual(len(cases),18)
        self.assertEqual(Counter(c['condition'] for c in cases),Counter({'S'+str(i):3 for i in range(6)}))
        self.assertEqual(blocks,schedule('normal'))
        self.assertEqual(blocks[0]['policy'],'INSTALLED')

    def test_challenge_keeps_recoverable_and_negative_cases_separate(self):
        cases=schedule('challenge')[0]['cases']
        self.assertEqual(len(cases),24)
        self.assertEqual(Counter(c['condition'] for c in cases),Counter({c:3 for c in
            ('delay','navdelay','drop','rollback','missing','duplicate','dirty','dirty-already-at-target')}))
        for c in cases:
            if c['condition']=='dirty-already-at-target':self.assertEqual(c['initial'],[1,60,1,1])

    def test_unknown_suite_is_rejected(self):
        with self.assertRaises(ValueError):schedule('unknown')


if __name__=='__main__':unittest.main()
