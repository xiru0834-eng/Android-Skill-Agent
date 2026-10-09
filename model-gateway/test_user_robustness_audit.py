import json
import shutil
import tempfile
import unittest
from pathlib import Path
from user_robustness_audit import audit

class AuditEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        source=Path(__file__).resolve().parents[1]/'evaluation/user-robustness/phone-normal'
        shutil.copytree(source/'run-000',self.root/'run-000')
        shutil.copyfile(source/'skill.json',self.root/'skill.json')
        self.rows=[json.loads((source/'results.json').read_text(encoding='utf-8'))[0]]
        self.put('results.json',self.rows);self.put('protocol.json',{'cases':[self.rows[0]['case']]})
    def put(self,name,value):(self.root/name).write_text(json.dumps(value),encoding='utf-8')
    def test_real_ledger_agrees(self):
        result=audit(self.root);self.assertEqual(0,result['inputMismatch']);self.assertEqual(0,result['lateInputs'])
    def test_tampered_success_is_rejected(self):
        self.rows[0]['confirmed_success']=not self.rows[0]['confirmed_success'];self.put('results.json',self.rows)
        with self.assertRaisesRegex(ValueError,'SCORE_MISMATCH'):audit(self.root)
    def test_changed_expected_initial_is_rejected(self):
        self.put('protocol.json',{'cases':[dict(self.rows[0]['case'],initial=[1,100,1,1])]})
        with self.assertRaisesRegex(ValueError,'SCHEDULE_CHANGED'):audit(self.root)

if __name__=='__main__':unittest.main()
