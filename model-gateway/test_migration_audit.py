import unittest
from migration_audit import check_schedule


class MigrationAuditTest(unittest.TestCase):
    def test_reordered_or_changed_cases_rejected(self):
        blocks = [dict(config='reference', cases=[dict(initial=[0,40,0,3], repeat=0)])]
        row = dict(config='reference', case=dict(initial=[0,40,0,3], repeat=0))
        check_schedule([row], blocks)
        with self.assertRaises(ValueError): check_schedule([dict(row, config='compact')], blocks)
        with self.assertRaises(ValueError): check_schedule([dict(row, case={})], blocks)
        with self.assertRaises(ValueError): check_schedule([row, row], blocks)

    def test_empty_partial_not_full_success(self):
        self.assertEqual(check_schedule([], [dict(config='reference', cases=[{}])]), 1)


if __name__ == '__main__': unittest.main()
