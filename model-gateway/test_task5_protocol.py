"""Task5 protocol/statistical boundaries; not phone experiments."""
import copy
import unittest
from task5_protocol import decode, safe_name, paired_plan, paired_stats, latency, stable_repeats


class ProtocolTests(unittest.TestCase):
    def test_json_rejects_duplicates_nonfinite_bad_utf8_and_secrets(self):
        for blob in [b'{"a":1,"a":2}', b'{"n":NaN}', b'\xff', b'{"authorization":"hidden"}']:
            with self.subTest(blob=blob), self.assertRaises(ValueError):decode(blob)
        self.assertEqual(decode(b'{"n":null}'), {'n':None})

    def test_file_size_and_paths(self):
        with self.assertRaises(ValueError):decode(b' '*8388609)
        for name in ['../a','/a','a\\b','a:b','a/./b','']:
            with self.subTest(name=name),self.assertRaises(ValueError):safe_name(name)

    def test_frozen_pairs_and_balanced_order(self):
        p=paired_plan({f:'a'*64 for f in ['S3','M1','M4']})
        self.assertEqual(len(p['cases']),36)
        self.assertEqual(len({r['id'] for r in p['cases']}),36)
        self.assertEqual(sum(r['order']==['A','B'] for r in p['cases']),18)
        self.assertTrue(all(r['budgetMs']==60000 for r in p['cases']))
        self.assertEqual(p,paired_plan({f:'a'*64 for f in ['S3','M1','M4']}))
        with self.assertRaises(ValueError):paired_plan({'S3':'a'*64})

    def test_paired_missing_rows_and_exact_discordance(self):
        p=paired_plan({f:'a'*64 for f in ['S3','M1','M4']})
        def row(i,arm,success):return dict(id=p['cases'][i]['id'],arm=arm,conditions=p['cases'][i],success=success,safetyChecked=True,safetyViolation=False)
        self.assertIsNone(paired_stats(p,[])['delta'])
        rows=sum(([row(i,'A',False),row(i,'B',True)] for i in range(6)),[])
        s=paired_stats(p,rows);self.assertEqual((s['n'],s['missingPairs'],s['bOnly']),(6,30,6))
        self.assertAlmostEqual(s['exactTwoSidedP'],.03125)
        self.assertEqual(s['conclusion'],'EXPLORATORY_ONLY')
        with self.assertRaises(ValueError):paired_stats(p,rows+[rows[0]])
        bad=copy.deepcopy(rows);bad[0]['conditions']['budgetMs']=60001
        with self.assertRaises(ValueError):paired_stats(p,bad)

    def test_unchecked_safety_cannot_imply_no_regression(self):
        p=paired_plan({f:'a'*64 for f in ['S3','M1','M4']})
        rows=[dict(id=p['cases'][0]['id'],arm=a,conditions=p['cases'][0],success=True,safetyChecked=False,safetyViolation=False) for a in ['A','B']]
        s=paired_stats(p,rows);self.assertEqual(s['safetyGate'],'UNVERIFIED')
        self.assertEqual(s['exactTwoSidedP'],1)

    def test_latency_nearest_rank_missing_and_strict_types(self):
        self.assertEqual(latency([],3)['missing'],3)
        self.assertEqual(latency([1,2,3,4],4)['p50Ms'],2)
        for values in [[True],[-1],[float('inf')]]:
            with self.subTest(values=values),self.assertRaises(ValueError):latency(values,1)

    def test_three_repeats_require_every_planned_trial(self):
        self.assertEqual(stable_repeats([('x',0,True),('x',1,True)],3)['allCorrect'],0)
        self.assertEqual(stable_repeats([('x',i,True) for i in range(3)],3)['allCorrect'],1)
        with self.assertRaises(ValueError):stable_repeats([('x',0,True),('x',0,True)],3)
