import copy
import json
import tempfile
import unittest
from pathlib import Path
from workflow_audit import audit
from workflow_score import score

class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.cases=[];self.rows=[]
        for i,policy in enumerate(('R1','P')):
            c=dict(pair='pair',policy=policy,layout='single',fault='normal',goal=[1,60,1,1],initial=[0,40,0,3])
            self.cases.append(c);run=str(i)*16;folder=self.root/str(i);folder.mkdir()
            self.put(folder/'case.json',dict(c,runId=run))
            initial=dict(ms=1,kind='initial',page='single',saved=c['initial'],draft=c['initial'],pending=0)
            final=dict(ms=50,kind='save',page='single',saved=c['goal'],draft=c['goal'],pending=0)
            oracle=dict(schema=1,caseId=run,layout='single',initial=c['initial'],events=[initial,final])
            self.put(folder/'before.json',dict(oracle,events=[initial]));self.put(folder/'oracle.json',oracle)
            result=dict(runId=run,goal=c['goal'],policy=policy,startedMs=10,finishedMs=60,deadlineMs=100,status='SUCCEEDED',actions=[])
            self.put(folder/'result.json',result);s=score(oracle,result,c['goal']);self.put(folder/'score.json',s)
            self.rows.append(dict(c,**s,expected_behavior=True,run_directory=str(i)))
        self.put(self.root/'protocol.json',dict(cases=self.cases,source_hashes={}))
        self.put(self.root/'results.json',self.rows)
    def tearDown(self):self.tmp.cleanup()
    def put(self,path,data):path.write_text(json.dumps(data),encoding='utf-8')
    def test_complete_pairs_pass(self):self.assertEqual(audit(self.root)['runs'],2)
    def test_missing_trial_fails(self):
        self.put(self.root/'results.json',self.rows[:1])
        with self.assertRaises(ValueError):audit(self.root)
    def test_wrong_layout_in_evidence_fails(self):
        path=self.root/'0/oracle.json';o=json.loads(path.read_text());o['layout']='multi';self.put(path,o)
        with self.assertRaises(ValueError):audit(self.root)
    def test_forged_summary_fails(self):
        rows=copy.deepcopy(self.rows);rows[0]['actual_success']=False;self.put(self.root/'results.json',rows)
        with self.assertRaises(ValueError):audit(self.root)

if __name__=='__main__':unittest.main()
