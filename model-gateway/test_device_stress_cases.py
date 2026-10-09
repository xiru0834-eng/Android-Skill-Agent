import unittest
from device_stress_cases import CONFIGS,valid_cases,safety_cases

class StressProtocolTest(unittest.TestCase):
    def test_ofat_each_config_has_one_factor(self):
        self.assertEqual(len({c['name'] for c in CONFIGS}),12)
        for c in CONFIGS:self.assertIn(c['factor'],('baseline','size','density','font','initial','injection'))
    def test_tasks_repeated_not_counted_as_new_kinds(self):
        rows=valid_cases(CONFIGS[0]);self.assertEqual(len(rows),60)
        self.assertEqual(len({r['case_id'] for r in rows}),60)
        self.assertEqual(len({r['case_id'].split('-')[0] for r in rows}),20)
    def test_initial_change_keeps_calls(self):
        a=valid_cases(CONFIGS[0]);b=valid_cases(CONFIGS[7])
        self.assertEqual([r['calls'] for r in a],[r['calls'] for r in b])
        self.assertTrue(all(r['initial']==[1,100,1,30] for r in b))
    def test_safety_cases_separate_and_no_retry_input(self):
        rows=safety_cases();self.assertEqual(len(rows),27)
        self.assertTrue(all(not r['positive'] for r in rows))
        self.assertEqual(sum(r['expected_inputs']==1 for r in rows),3)
if __name__=='__main__':unittest.main()
