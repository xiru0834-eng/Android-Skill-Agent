import unittest
from audit_transfer import verify_row


class AuditTests(unittest.TestCase):
    def row(self):
        return dict(case=dict(method='skill',negative=False,initial=[False,False],mode='normal'),
            before=dict(target=False,other=False,targetClicks=0,otherClicks=0,mode='normal'),
            after=dict(target=True,other=True,targetClicks=1,otherClicks=1,mode='normal'),
            report=dict(status='SUCCEEDED',desired=[True,True],inputs=2,elapsedMs=1800),
            actualGoal=True,confirmed=True,falseSuccess=False,issuedInputs=2,
            expectedClicks=[1,1],observedClicks=[1,1],extraInputs=0,inputsMatch=True,**{'pass':True})

    def test_accepts_consistent_record(self):
        verify_row(self.row())

    def test_detects_result_falsely_marked_success(self):
        row=self.row();row['after']['other']=False
        with self.assertRaises(ValueError):verify_row(row)

    def test_detects_wrong_initial_state(self):
        row=self.row();row['before']['target']=True
        with self.assertRaises(ValueError):verify_row(row)
