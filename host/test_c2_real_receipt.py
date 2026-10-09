"""Replay immutable real native receipts; no device or model call."""
import copy,json,unittest
from pathlib import Path
from c2_validation import checked_receipt
ROOT=Path('C:/Users/zz/Documents/ChatGPT/毕设/tasks/C2-identity-wireup/20261009-r1/normal-journey-r3/validation-r2')
class RealReceiptTests(unittest.TestCase):
    def setUp(self):
        self.receipt=json.loads((ROOT/'60-native.json').read_text(encoding='utf-8'))['native']
        self.plan=json.loads(self.receipt['native_plan_raw'])
    def check(self,r):return checked_receipt(r,self.plan,r['candidate_id'],r['request_id'])
    def test_real_local_effect_followed_by_full_after_and_final(self):
        for value in (60,20,80):
            r=json.loads((ROOT/(str(value)+'-native.json')).read_text(encoding='utf-8'))['native'];p=json.loads(r['native_plan_raw'])
            calls=checked_receipt(r,p,r['candidate_id'],r['request_id']);self.assertEqual(calls[0]['args']['percent'],value)
    def test_partial_effect_cannot_replace_full_after(self):
        r=copy.deepcopy(self.receipt)
        o=next(o for o in r['observations'] if o['phase'].startswith('AFTER.'));o['complete']=False
        with self.assertRaises(ValueError):self.check(r)
    def test_partial_effect_wrong_value_rejected(self):
        r=copy.deepcopy(self.receipt)
        s=next(s for s in r['steps'] if s['op']=='CALL');s['runtime_receipt']['execution_actions'][0]['effect_observed_state']['bedroom_light.brightnessPercent']=59
        with self.assertRaises(ValueError):self.check(r)
    def test_partial_effect_unknown_extra_value_rejected(self):
        r=copy.deepcopy(self.receipt)
        s=next(s for s in r['steps'] if s['op']=='CALL');s['runtime_receipt']['execution_actions'][0]['effect_observed_state']['unrelated.secret']=60
        with self.assertRaises(ValueError):self.check(r)
    def test_partial_effect_does_not_waive_final(self):
        r=copy.deepcopy(self.receipt);r['final_observation_complete']=False
        with self.assertRaises(ValueError):self.check(r)
    def test_partial_effect_ack_is_not_effect_evidence(self):
        r=copy.deepcopy(self.receipt)
        s=next(s for s in r['steps'] if s['op']=='CALL');s['runtime_receipt']['execution_actions'][0]['effect_verified']=False
        with self.assertRaises(ValueError):self.check(r)
    def test_late_partial_effect_rejected(self):
        r=copy.deepcopy(self.receipt)
        s=next(s for s in r['steps'] if s['op']=='CALL');s['runtime_receipt']['execution_actions'][0]['effect_observation_ms']=10**15
        with self.assertRaises(ValueError):self.check(r)
if __name__=='__main__':unittest.main()
