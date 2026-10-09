"""Test scorer/inventory rules before the formal batch; no Android calls."""
import unittest
from acceptance_tools import classify_backup, compare_protection, score_flow, assert_readonly_proof, verified_file_digest


class AcceptanceToolsTest(unittest.TestCase):
    def test_missing_backup_error_is_not_skill_data(self):
        self.assertEqual(classify_backup(b'cat: files/a.json: No such file or directory\r\n')['status'], 'NOT_PRESENT')

    def test_real_json_is_present(self):
        self.assertEqual(classify_backup(b'{"saved":true}')['bytes'], 14)

    def test_protection_missing_stays_missing(self):
        before={'a':{'status':'NOT_PRESENT'},'b':{'status':'PRESENT','sha256':'1'}}
        self.assertEqual(compare_protection(before,before)['verdict'],'PASS')

    def test_protection_drift_not_hidden(self):
        before={'a':{'status':'PRESENT','sha256':'1'}}
        self.assertEqual(compare_protection(before,{'a':{'status':'PRESENT','sha256':'2'}})['verdict'],'FAIL')

    def test_flow_success_requires_all_steps_and_no_writes(self):
        s={'status':'PASS','observations':5,'real_navigation_actions':4,'interactions_verified':4}
        audit={'write_count':0,'pending_count':0,'state_unchanged':True}
        self.assertTrue(score_flow(s,audit)['correct'])
        s['interactions_verified']=3
        self.assertFalse(score_flow(s,audit)['correct'])

    def test_declared_success_not_enough(self):
        s={'status':'PASS','observations':5,'real_navigation_actions':4,'interactions_verified':4}
        a={'write_count':1,'pending_count':0,'state_unchanged':False}
        self.assertFalse(score_flow(s,a)['correct'])

    def test_readonly_false_counter_blocked(self):
        with self.assertRaises(ValueError):
            assert_readonly_proof({'native_counters_unchanged':False,'business_ledger_unchanged':True,'query_calls':4})
    def test_transport_length_mismatch_is_not_data(self):
        with self.assertRaises(ValueError):verified_file_digest(b'line\r\n',5)
    def test_verified_original_bytes(self):
        self.assertEqual(verified_file_digest(b'line\n',5)['bytes'],5)


if __name__=='__main__':unittest.main()
