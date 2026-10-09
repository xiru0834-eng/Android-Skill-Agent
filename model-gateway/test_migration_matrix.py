import unittest
from migration_matrix import make_blocks, summarize, effective_display_value, remaining_blocks


class MigrationMatrixTest(unittest.TestCase):
    def test_resume_does_not_replace_failed_attempt(self):
        original = make_blocks()
        pending = remaining_blocks(original, 7)
        all_cases = [(b['config'], c) for b in original for c in b['cases']]
        rest = [(b['config'], c) for b in pending for c in b['cases']]
        self.assertEqual(rest, all_cases[7:])
        self.assertEqual(sum(len(b['cases']) for b in original), 72)
        with self.assertRaises(ValueError): remaining_blocks(original, -1)
        with self.assertRaises(ValueError): remaining_blocks(original, 73)

    def test_override_not_masked_by_physical_size(self):
        self.assertEqual(effective_display_value('Physical size: 1080x2400\nOverride size: 720x1280\n'), '720x1280')
        self.assertEqual(effective_display_value('Physical density: 420\n'), '420')
        with self.assertRaises(ValueError): effective_display_value('Error: unavailable')

    def test_balanced_and_repeatable(self):
        blocks = make_blocks()
        self.assertEqual(blocks, make_blocks())
        self.assertEqual(len(blocks), 12)
        for config in ('reference', 'same-dp', 'compact', 'wide'):
            rows = [c for b in blocks if b['config'] == config for c in b['cases']]
            self.assertEqual(len(rows), 18)
            for initial in range(6):
                self.assertEqual(sum(c['initialId'] == 'S'+str(initial) for c in rows), 3)

    def test_missing_evidence_not_success(self):
        rows = [dict(config='reference', case=dict(initialId='S0'), evidence_complete=False,
                     confirmed_success=True, infrastructureFailure='launch')]
        report = summarize(rows, 72)
        self.assertEqual(report['confirmed'], 0)
        self.assertEqual(report['attempted'], 1)
        self.assertEqual(report['unrun'], 71)
        self.assertEqual(report['infrastructureFailures'], 1)

    def test_noop_separate_from_input(self):
        rows = [dict(config='reference', case=dict(initialId=s), evidence_complete=True,
                     confirmed_success=True, false_success=False, elapsed_ms=1000)
                for s in ('S0', 'S5')]
        report = summarize(rows, 72)['byConfig']['reference']
        self.assertEqual(report['needsInput']['confirmed'], 1)
        self.assertEqual(report['already']['confirmed'], 1)


if __name__ == '__main__': unittest.main()
