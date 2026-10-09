import copy
import unittest
from closeout_confirmation import cases_for, summary
from accuracy_confirmation import adjudicate
from test_entry_confirmation import BASE


class CloseoutTests(unittest.TestCase):
    def test_actual_catalog_only_balanced_and_no_mutation(self):
        before=copy.deepcopy(BASE);cases=cases_for(BASE)
        self.assertEqual(BASE,before)
        self.assertEqual(len(cases),60)
        self.assertEqual(len({c['text'] for c in cases}),60)
        for case in cases:
            self.assertEqual({s['id'] for s in case['skills']},{s['id'] for s in BASE})
            self.assertIn(case['expected'],[None]+[s['id'] for s in BASE])
        for lang in ['zh','en']:
            self.assertTrue(any(c['language']==lang and c['expected'] for c in cases))
            self.assertEqual(sum(c['language']==lang and c['expected'] is not None for c in cases),15)

    def test_gate_requires_all_trials_zero_unsafe_and_availability(self):
        cases=cases_for(BASE);rows=[]
        for repeat in range(3):
            for case in cases:
                rows.append(adjudicate(dict(case=case,strategy='G',repeat=repeat,available=True,
                    selection=dict(status='invoke' if case['expected'] else 'reject',skill_id=case['expected'],message='Test'),
                    ms=10,remoteCalls=1,calls=[])))
        self.assertTrue(summary(rows)['stageLanguageGate'])
        self.assertFalse(summary(rows[:-1])['stageLanguageGate'])
        bad=copy.deepcopy(rows)
        for row in bad[:4]:row.update(available=False,selection={});adjudicate(row)
        self.assertFalse(summary(bad)['stageLanguageGate'])
        bad=copy.deepcopy(rows);negative=next(r for r in bad if r['case']['expected'] is None)
        negative['selection']=dict(status='invoke',skill_id=BASE[0]['id'],message='Wrong');adjudicate(negative)
        self.assertFalse(summary(bad)['stageLanguageGate'])


if __name__=='__main__':unittest.main()
