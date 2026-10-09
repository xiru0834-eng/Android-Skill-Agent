import unittest
from evaluate_fixture_dataset import evaluate


class DatasetTests(unittest.TestCase):
    def test_all_annotated_known_samples_stay_in_denominator_and_are_correct(self):
        report = evaluate()
        self.assertEqual(report['positive_samples'],14); self.assertEqual(report['correct_positive_samples'],14)
        self.assertEqual(report['positive_unknown_samples'],0); self.assertEqual(report['correct_rejections'],6)
        self.assertEqual(report['visible_target_recall'],1); self.assertEqual(report['visible_target_precision'],1)
        self.assertTrue(all(row['correct'] and row['visible_targets_correct'] for row in report['rows']))
        self.assertEqual(report['device_observations'],0); self.assertEqual(report['model_calls'],0)


if __name__ == '__main__': unittest.main()
