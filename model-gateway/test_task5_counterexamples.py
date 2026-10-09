import unittest
from task5_counterexamples import specimen,experiment
from task5_evidence import judge_run


class CounterexampleTests(unittest.TestCase):
    def test_specimen_is_complete_under_existing_contract(self):
        r=judge_run(specimen());self.assertEqual(r['state'],'PASS',r['errors'])

    def test_every_frozen_software_case_has_expected_class(self):
        r=experiment();self.assertEqual(r['n'],21)
        self.assertEqual(r['matches'],21,[x for x in r['rows'] if not x['matches']])
