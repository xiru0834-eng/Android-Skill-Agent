import copy
import unittest
from jev_selection_benchmark import cases,summarize

CATALOG=[dict(id=hex(i+1)[2:]*64,name=n,goal=n,finalGoals=g) for i,(n,g) in enumerate([
    ('Transfer Bench',[1,100,1,1]),('Reading60',[1,60,1,1]),('Bright80',[1,80,1,3]),('LampOnly60',[1,60,None,None]),('FanOnlyLow',[None,None,1,1])])]

class BenchmarkTests(unittest.TestCase):
    def test_balanced_distinct_categories(self):
        rows=cases(CATALOG)
        self.assertEqual(len(rows),40);self.assertEqual(sum(r['language']=='zh' for r in rows),20)
        self.assertEqual(sum(r['expected'] is not None for r in rows),20)
        self.assertEqual(len({r['text'] for r in rows}),40)
    def test_repeat_cluster_summary_and_errors_retained(self):
        c=cases(CATALOG)[0];protocol=dict(cases=[c],trials=[dict(case=c,repeat=i) for i in range(3)])
        rows=[]
        for i in range(3):
            for backend in ('gpt','jev'):
                correct=backend=='gpt' or i!=0
                rows.append(dict(case=c,repeat=i,backend=backend,correct=correct,unsafeSuggestion=False,available=correct,ms=1000 if backend=='gpt' else 100,selection=dict(status='invoke' if correct else 'clarify',skill_id=c['expected'] if correct else None)))
        summary=summarize(rows,protocol)
        self.assertEqual(summary['gpt']['correct'],3);self.assertEqual(summary['jev']['correct'],2)
        self.assertEqual(summary['jev']['errors'],1);self.assertEqual(summary['jev']['n'],3)
        self.assertAlmostEqual(summary['paired']['correctnessDifference'],-1/3)
        self.assertEqual(summary['gpt']['consistentCases'],1);self.assertEqual(summary['jev']['consistentCases'],0)

if __name__=='__main__':unittest.main()
