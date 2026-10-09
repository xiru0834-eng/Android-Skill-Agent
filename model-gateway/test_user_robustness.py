import unittest
from user_robustness import phone_cases, display_cases, expectation, CONFIGS

class MatrixTests(unittest.TestCase):
    def test_all_sixteen_masks_twice(self):
        rows=phone_cases('normal')
        self.assertEqual(32,len(rows))
        self.assertEqual(16,len({tuple(r['initial']) for r in rows}))
        for r in rows:self.assertEqual(2,sum(x['initial']==r['initial'] for x in rows))
        self.assertEqual(rows,phone_cases('normal'))
    def test_challenge_separate(self):
        rows=phone_cases('challenge')
        self.assertEqual(14,len(rows))
        self.assertEqual(4,sum(r['expect']=='SUCCEEDED' for r in rows))
    def test_display_cross_product(self):
        rows=display_cases()
        self.assertEqual(24,len(rows))
        for c in CONFIGS:self.assertEqual(6,sum(r['config']==c for r in rows))
    def test_false_success_never_passes(self):
        r=dict(status='SUCCEEDED',confirmed_success=True,false_success=True)
        self.assertFalse(expectation(r,dict(expect='SUCCEEDED'),True,dict(unexpectedIds=0,afterDeadlineInputs=0)))
    def test_refusal_not_normal_success(self):
        r=dict(status='UNCONFIRMED',confirmed_success=False,false_success=False)
        self.assertFalse(expectation(r,dict(expect='SUCCEEDED'),True,dict(unexpectedIds=0,afterDeadlineInputs=0)))
        self.assertTrue(expectation(r,dict(expect='UNCONFIRMED'),True,dict(unexpectedIds=0,afterDeadlineInputs=0)))
    def test_bad_input_never_passes(self):
        r=dict(status='SUCCEEDED',confirmed_success=True,false_success=False)
        self.assertFalse(expectation(r,dict(expect='SUCCEEDED'),True,dict(unexpectedIds=1,afterDeadlineInputs=0)))
    def test_wrong_failure_reason_is_not_a_pass(self):
        r=dict(status='UNCONFIRMED',confirmed_success=False,false_success=False,reason='WRONG_APP')
        self.assertFalse(expectation(r,dict(expect='UNCONFIRMED',expectedReason='STEP_UNCONFIRMED'),True,dict(unexpectedIds=0,afterDeadlineInputs=0)))

if __name__=='__main__':unittest.main()
