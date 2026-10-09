import copy,json,unittest
from pathlib import Path
from partial_audit import check_run

class PartialAuditTests(unittest.TestCase):
    def setUp(self):
        folder=Path(__file__).resolve().parents[1]/'evaluation/partial-workflow/phone-matrix/run-000'
        self.d={p.stem:json.loads(p.read_text(encoding='utf-8')) for p in folder.glob('*.json')}
    def test_real_record(self):self.assertTrue(check_run(self.d,self.d['case'])['passCriteria'])
    def test_changed_score_rejected(self):
        self.d['score']['non_target_violation']=True
        with self.assertRaises(ValueError):check_run(self.d,self.d['case'])
    def test_changed_schedule_rejected(self):
        case=copy.deepcopy(self.d['case']);case['initial'][2]=1
        with self.assertRaises(ValueError):check_run(self.d,case)
    def test_removed_input_request_rejected(self):
        self.d['journal']=[e for e in self.d['journal'] if e['kind']!='INPUT_REQUEST']
        with self.assertRaises(ValueError):check_run(self.d,self.d['case'])
    def test_changed_preserved_goal_rejected(self):
        self.d['terminal']['goal'][2]=1
        with self.assertRaises((ValueError,AssertionError)):check_run(self.d,self.d['case'])
    def test_forged_trace_rejected(self):
        self.d['skill']['traceId']='not-the-trace'
        with self.assertRaises(ValueError):check_run(self.d,self.d['case'])
