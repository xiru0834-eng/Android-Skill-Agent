import unittest
from jev_reliability import build_cases, score, summarize, hybrid
from test_jev_benchmark import CATALOG


class ReliabilityTests(unittest.TestCase):
    def test_dataset_balanced_distinct_and_catalog_variants(self):
        rows = build_cases(CATALOG)
        self.assertEqual(len(rows), 48)
        self.assertEqual(len({c['text'] for c in rows}), 48)
        self.assertEqual(sum(c['expected'] is not None for c in rows), 24)
        self.assertEqual(sum(c['language'] == 'zh' for c in rows), 24)
        self.assertEqual(max(len(c['skills']) for c in rows), 20)
        self.assertNotEqual(rows[4]['skills'][0]['id'], CATALOG[0]['id'])

    def test_api_error_is_not_correct_negative_or_consistent_success(self):
        case = dict(caseId='x', expected=None, expectedStatus='reject', language='en', category='error', variant='base')
        row = dict(available=False, ms=2, backend='jev', error='HTTP_429', case=case, repeat=0)
        self.assertFalse(score(row)['correct'])
        summary = summarize([score(row)], {'cases': [case], 'repeats': 2})
        self.assertEqual(summary['jev']['errors'], 1)
        self.assertEqual(summary['jev']['consistentCases'], 0)

    def test_wrong_high_confidence_invoke_is_never_correct(self):
        case = dict(caseId='x', expected='a'*64, expectedStatus='invoke', language='en', category='p', variant='base')
        row = score(dict(case=case, repeat=0, backend='jev', available=True, ms=10,
            selection=dict(status='invoke', skill_id='b'*64), metadata=dict(answer=dict(confidence=.999))))
        self.assertFalse(row['correct']); self.assertTrue(row['unsafeSuggestion'])

    def test_hybrid_replay_counts_risk_and_summed_not_parallel_latency(self):
        c = dict(caseId='x', expected=None, expectedStatus='clarify', language='en', category='n', variant='base')
        j = score(dict(case=c, repeat=0, backend='jev', available=True, ms=100, selection=dict(status='clarify', skill_id=None)))
        g = score(dict(case=c, repeat=0, backend='gpt', available=True, ms=900, selection=dict(status='invoke', skill_id='a'*64)))
        h = hybrid([j, g])[0]
        self.assertEqual(h['ms'], 1000); self.assertTrue(h['unsafeSuggestion'])
        self.assertTrue(h['offlineCounterfactual'])


if __name__ == '__main__': unittest.main()
