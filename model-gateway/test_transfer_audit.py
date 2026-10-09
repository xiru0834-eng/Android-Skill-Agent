import copy
import unittest
from transfer_audit import evaluate

def sample():
    goal=[1,60,1,1]
    events=[dict(ms=0,kind='initial',page='overview',saved=[0,40,0,3],draft=[0,40,0,3],pending=0),
            dict(ms=100,kind='save',page='overview',saved=goal,draft=goal,pending=0)]
    oracle=dict(schema=1,caseId='case1',initial=[0,40,0,3],events=events)
    result=dict(runId='run1',startedMs=10,finishedMs=200,deadlineMs=30000,status='SUCCEEDED',actions=[])
    audits=[dict(capturedMs=t,oracle=copy.deepcopy(oracle)) for t in (201,1200,5300)]
    return oracle,result,goal,audits

class AuditTests(unittest.TestCase):
    def run_score(self,items):return evaluate(*items,case_id='case1',run_id='run1')
    def test_good(self):self.assertTrue(self.run_score(sample())['confirmed_success'])
    def test_no_audit_is_unknown(self):
        o,r,g,a=sample();self.assertRaises(ValueError,evaluate,o,r,g,[],case_id='case1',run_id='run1')
    def test_wrong_run(self):
        o,r,g,a=sample();r['runId']='stale';self.assertRaises(ValueError,self.run_score,(o,r,g,a))
    def test_wrong_case(self):
        o,r,g,a=sample();a[1]['oracle']['caseId']='other';self.assertRaises(ValueError,self.run_score,(o,r,g,a))
    def test_late_commit_not_success(self):
        o,r,g,a=sample();o['events'][1]['ms']=250
        a=[dict(capturedMs=x['capturedMs'],oracle=copy.deepcopy(o)) for x in a]
        self.assertTrue(self.run_score((o,r,g,a))['false_success'])
    def test_rollback(self):
        o,r,g,a=sample();bad=copy.deepcopy(o['events'][-1]);bad.update(ms=1000,saved=[0,60,1,1],draft=[0,60,1,1])
        o['events'].append(bad);a[-1]['oracle']=copy.deepcopy(o)
        self.assertTrue(self.run_score((o,r,g,a))['false_success'])
    def test_no_success_claim(self):
        o,r,g,a=sample();r['status']='UNCONFIRMED';self.assertTrue(self.run_score((o,r,g,a))['unconfirmed_success'])
    def test_inconsistent_snapshot(self):
        o,r,g,a=sample();a[-1]['oracle']['events'][1]['saved']=[0,60,1,1]
        self.assertRaises(ValueError,self.run_score,(o,r,g,a))
    def test_short_audit(self):
        o,r,g,a=sample();a[-1]['capturedMs']=3000;self.assertRaises(ValueError,self.run_score,(o,r,g,a))

if __name__=='__main__':unittest.main()
