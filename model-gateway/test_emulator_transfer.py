import unittest
from emulator_transfer import schedule, score, summary


class TransferTests(unittest.TestCase):
    def test_balanced_reproducible_pairs(self):
        rows = schedule(5)
        self.assertEqual(rows, schedule(5))
        self.assertEqual(len(rows), 140)
        for a, b in zip(rows[::2], rows[1::2]):
            self.assertEqual((a['profile'], a['name'], a['rep']), (b['profile'], b['name'], b['rep']))
            self.assertEqual({a['method'], b['method']}, {'skill', 'coordinate'})
        self.assertEqual(sum(r['negative'] and r['method']=='skill' for r in rows), 10)

    def test_coordinate_cannot_claim_confirmation_or_false_success(self):
        case = dict(method='coordinate', negative=False, initial=[True,False])
        state = dict(target=False, other=True, targetClicks=1, otherClicks=1)
        result = score(case, state, None)
        self.assertFalse(result['actualGoal'])
        self.assertIsNone(result['falseSuccess'])
        self.assertEqual(result['extraInputs'], 1)
        self.assertEqual(result['issuedInputs'], 2)

    def test_skill_requires_actual_goal_and_exact_inputs(self):
        case = dict(method='skill', negative=False, initial=[False,False])
        state = dict(target=True, other=False, targetClicks=1, otherClicks=1)
        report = dict(status='SUCCEEDED', desired=[True,True], inputs=2, elapsedMs=900)
        self.assertTrue(score(case,state,report)['falseSuccess'])
        self.assertFalse(score(case,state,report)['pass'])
        self.assertTrue(score(case,{**state,'other':True},report)['pass'])

    def test_negative_requires_no_inputs_and_refusal(self):
        case = dict(method='skill', negative=True, initial=[False,False])
        state = dict(target=False, other=False, targetClicks=0, otherClicks=0)
        report = dict(status='REFUSED', desired=[True,True], inputs=0, elapsedMs=850)
        self.assertTrue(score(case,state,report)['pass'])
        self.assertFalse(score(case,state,{**report,'inputs':1})['pass'])

    def test_empty_summary_does_not_invent_latency(self):
        self.assertIsNone(summary([])['skill']['p50ms'])
        self.assertEqual(summary([])['completed'], 0)

    def test_negative_coordinate_inputs_count_even_if_they_miss_controls(self):
        case = dict(method='coordinate', negative=True, initial=[False,False])
        state = dict(target=False, other=False, targetClicks=0, otherClicks=0)
        self.assertEqual(score(case,state,None)['extraInputs'], 2)


if __name__ == '__main__': unittest.main()
