import unittest
from test_skill_selection import CATALOG
from model_coordination import measure,score
from compiler import ModelError


class CoordinationMeasurementTests(unittest.TestCase):
    def test_holdout_import_does_not_change_main_strategy_matrix(self):
        import coordination_holdout
        from model_coordination import STRATEGIES
        self.assertEqual(set(STRATEGIES),{'G','J','C','R'})

    def test_full_candidate_measurement_has_no_remote_for_literal_name(self):
        from start_teaching_bridge import resolve_selector
        row=measure('F','执行阅读60',CATALOG,lambda _:self.fail('API invoked'),selector=resolve_selector('routed'))
        self.assertEqual(row['route'],'literal-name')
        self.assertEqual(row['remoteCalls'],0)
    def test_name_measurement_must_record_no_api(self):
        row=measure('R','执行阅读60',CATALOG,lambda _:self.fail('API invoked'))
        self.assertTrue(row['available']);self.assertEqual(row['remoteCalls'],0)
        self.assertEqual(row['route'],'literal-name')
        self.assertEqual(row['inputTokens'],0)

    def test_error_is_not_a_correct_negative_or_unsafe_invoke(self):
        def fail(_):raise ModelError('HTTP_429')
        row=measure('C','anything else',CATALOG,fail)
        row['case']=dict(expected=None)
        got=score(row)
        self.assertFalse(got['correct']);self.assertFalse(got['unsafeSuggestion'])
        self.assertEqual(got['remoteCalls'],1)

    def test_wrong_registered_id_is_not_correct(self):
        row=dict(available=True,case=dict(expected='a'*64),selection=dict(status='invoke',skill_id='b'*64))
        self.assertFalse(score(row)['correct']);self.assertTrue(row['unsafeSuggestion'])


if __name__=='__main__':unittest.main()
