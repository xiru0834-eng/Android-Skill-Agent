import unittest
from collections import Counter
from transfer_cases import make_cases

class CaseTests(unittest.TestCase):
    def test_normal_balanced(self):
        rows=make_cases('normal',10)
        self.assertEqual(len(rows),60)
        self.assertEqual(set(Counter(r['initialId'] for r in rows).values()),{10})
    def test_fault_cross_product_includes_counterexample(self):
        rows=make_cases('challenge',6)
        self.assertEqual(len(rows),48)
        self.assertEqual(sum(r['fault']=='dirty' and r['initial']==[1,60,1,1] for r in rows),6)
        self.assertEqual(set(Counter(r['condition'] for r in rows).values()),{6})
    def test_reproducible_order(self):self.assertEqual(make_cases('normal',3),make_cases('normal',3))

if __name__=='__main__':unittest.main()
