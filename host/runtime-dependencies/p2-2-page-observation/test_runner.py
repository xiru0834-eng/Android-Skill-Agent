"""Local freeze/score protocol checks; no device experiment dispatch."""
import unittest
from run_checks import check_freeze, plan


class RunnerTests(unittest.TestCase):
    def test_fresh_plan_matches_all_inputs_and_duplicate_cases_are_not_allowed(self):
        frozen = plan(); check_freeze(frozen)
        frozen['cases'].append(frozen['cases'][0])
        with self.assertRaisesRegex(ValueError,'FROZEN_TESTS_CHANGED'): check_freeze(frozen)

    def test_missing_source_pin_or_forged_scoring_boundary_blocks(self):
        for key, value in [('files',[]),('threshold','ALLOW_PARTIAL'),('model_calls',1),('device_actions',1),('configuration',{})]:
            frozen = plan(); frozen[key] = value
            with self.subTest(field=key), self.assertRaises(ValueError): check_freeze(frozen)

    def test_source_hash_change_is_detected_without_running_modified_suite(self):
        frozen = plan(); frozen['files'][0]['sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError,'FROZEN_FILE_CHANGED'): check_freeze(frozen)


if __name__ == '__main__': unittest.main()
