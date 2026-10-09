import copy,json,unittest
from pathlib import Path
from repair_scorer import score,ledger
ROOT=Path(__file__).parent

class ScorerChecks(unittest.TestCase):
    def setUp(self):
        self.row=json.loads((ROOT/'evidence/g3-phone-normal-ui-r9-default-r15/explicit.json').read_text(encoding='utf-8'))
        self.assertTrue(score(self.row)['passed'])
    def test_value_only_is_not_success(self):
        self.row['ui']['result']['completed_steps']=2
        self.assertTrue(score(self.row)['false_success'])
    def test_wrong_then_restored(self):
        self.row['after']['events'].extend([{'property':'bedroom_ac.power','value':'on'},{'property':'bedroom_ac.power','value':'off'}])
        self.assertTrue(score(self.row)['wrong_action'])
    def test_order_not_collapsed(self):
        self.row['ui']['result']['steps'].reverse()
        self.assertFalse(score(self.row)['passed'])
    def test_deadline_expired(self):
        self.row['ui']['result']['latency']['runtime_ms']=8000
        self.assertTrue(score(self.row)['false_success'])
    def test_oracle_conflict(self):
        self.row['after']['state']['bedroom_light.brightnessPercent']=60
        self.assertTrue(score(self.row)['false_success'])
    def test_missing_final_audit(self):
        self.row['ui']['result']['observations']=[]
        self.assertFalse(score(self.row)['passed'])
    def test_missing_duplicate_rows(self):
        r={'result':self.row['ui']['result']}
        self.assertFalse(ledger([r],2)['complete'])
        self.assertEqual(ledger([r,r],2)['duplicate_task_ids'],1)
    def test_noop_cannot_fake_speed(self):
        self.row['expected']='NO_ACTION_REQUIRED';self.row['final_status']='NO_ACTION_REQUIRED'
        self.assertFalse(score(self.row)['passed'])
    def test_cancel_late_input(self):
        self.row['expected']='CANCELLED';self.row['final_status']='USER_CANCELLED'
        self.row['ui']['late_callback_wait_ms']=20000
        self.assertFalse(score(self.row)['passed'])

if __name__=='__main__':unittest.main()
