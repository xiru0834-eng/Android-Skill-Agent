import copy
import unittest
from entry_confirmation import cases_for,summarize
from entry_confirmation_cases import SPECS
from accuracy_confirmation import adjudicate

BASE=[dict(id=str(i)*64,name=name,goal='Target',finalGoals=g) for i,(name,g) in enumerate([
    ('阅读60 / Reading60',[1,60,1,1]),('明亮80 / Bright80',[1,80,1,3]),('只灯60 / LampOnly60',[1,60,None,None]),
    ('只风扇低档 / FanOnlyLow',[None,None,1,1]),('满亮100 / Full100',[1,100,1,1])],1)]

class ConfirmationTests(unittest.TestCase):
    def rows(self):
        cases=cases_for(BASE);rows=[]
        for repeat in range(3):
            for case in cases:
                selection=dict(status='invoke' if case['expected'] else 'reject',skill_id=case['expected'],message='Review')
                rows.append(adjudicate(dict(case=case,strategy='G',repeat=repeat,selection=selection,available=True,
                    ms=1,remoteCalls=1,calls=[],inputTokens=0,outputTokens=0,route='remote')))
        return cases,rows
    def test_balanced_finite_prospective_cases(self):
        cases=cases_for(BASE)
        self.assertEqual((len(SPECS),len(cases),len({c['text'] for c in cases})),(30,60,60))
        for lang in ['zh','en']:
            self.assertEqual(sum(c['language']==lang and c['expected'] is not None for c in cases),15)
            self.assertEqual(sum(c['language']==lang and c['expected'] is None for c in cases),15)
    def test_gate_needs_complete_positive_recall_and_zero_unsafe(self):
        cases,rows=self.rows();protocol=dict(cases=cases)
        self.assertTrue(summarize(rows,protocol)['gatePassed'])
        self.assertFalse(summarize(rows[:-1],protocol)['gatePassed'])
        bad=copy.deepcopy(rows);bad[30]['selection']=dict(status='invoke',skill_id='1'*64,message='wrong');adjudicate(bad[30])
        self.assertFalse(summarize(bad,protocol)['gatePassed'])
        bad=copy.deepcopy(rows)
        failures=[r for r in bad if r['case']['expected'] and r['case']['language']=='zh'][:3]
        for r in failures:r['selection']=dict(status='clarify',skill_id=None,message='No');adjudicate(r)
        self.assertFalse(summarize(bad,protocol)['gatePassed'])

if __name__=='__main__':unittest.main()
