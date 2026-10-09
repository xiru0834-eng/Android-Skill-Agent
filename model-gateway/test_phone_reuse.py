import unittest
from unittest.mock import patch
from phone_reuse import judge, reset_fixture


class PhoneScoreTests(unittest.TestCase):
    def test_negative_fixture_reset_does_not_require_missing_nodes(self):
        oracle = dict(mode='missing_second', target=False, other=False, targetClicks=0, otherClicks=0)
        with patch('phone_reuse.d.s.adb'), patch('phone_reuse.d.oracle', return_value=oracle), \
             patch('phone_reuse.d.s.ui', side_effect=AssertionError('Must not inspect missing node')):
            self.assertEqual(reset_fixture('missing_second', [False,False]), oracle)

    def test_success_requires_oracle_and_requested_parameters(self):
        case = dict(initial=[False,True], desired=[True,True], mode='normal')
        oracle = dict(target=True, other=True, targetClicks=1, otherClicks=0)
        report = dict(status='SUCCEEDED', desired=[True,True], inputs=1)
        self.assertTrue(judge(case, report, oracle)['pass'])
        self.assertFalse(judge(case, {**report, 'desired':[False,True]}, oracle)['pass'])
        self.assertTrue(judge(case, report, {**oracle, 'target':False})['falseSuccess'])
        self.assertFalse(judge(case, report, {**oracle, 'otherClicks':1})['pass'])

    def test_negative_must_refuse_without_inputs(self):
        case = dict(initial=[False,False], desired=[True,True], mode='missing_second')
        oracle = dict(target=False, other=False, targetClicks=0, otherClicks=0)
        report = dict(status='REFUSED', desired=[True,True], inputs=0)
        self.assertTrue(judge(case, report, oracle)['pass'])
        self.assertFalse(judge(case, {**report, 'inputs':1}, oracle)['pass'])
