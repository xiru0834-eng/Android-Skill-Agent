import copy
import json
import unittest
from pathlib import Path
from named_journey_audit import check_run

class NamedAuditTests(unittest.TestCase):
    def setUp(self):
        folder=Path(__file__).resolve().parents[1]/'evaluation/named-journey/phone-confirmation/run-000'
        self.data={p.stem:json.loads(p.read_text(encoding='utf-8')) for p in folder.glob('*.json')}
    def test_actual_evidence(self):
        r=check_run(self.data,self.data['case']);self.assertTrue(r['inputLedgerMatch'])
    def test_fake_success_rejected(self):
        self.data['score']['actual_success']=False
        with self.assertRaisesRegex(ValueError,'SCORE_MISMATCH'):check_run(self.data,self.data['case'])
    def test_skill_change_rejected(self):
        self.data['skill']['traceSha256']='0'*64
        with self.assertRaisesRegex(ValueError,'SKILL_CHANGED'):check_run(self.data,self.data['case'])
    def test_schedule_change_rejected(self):
        case=copy.deepcopy(self.data['case']);case['initial']=[1,60,1,1]
        with self.assertRaisesRegex(ValueError,'SCHEDULE_CHANGED'):check_run(self.data,case)
    def test_missing_input_record_rejected(self):
        self.data['journal']=[j for j in self.data['journal'] if j['kind']!='INPUT_REQUEST']
        with self.assertRaisesRegex(ValueError,'JOURNAL_IDENTITY'):check_run(self.data,self.data['case'])

if __name__=='__main__':unittest.main()
