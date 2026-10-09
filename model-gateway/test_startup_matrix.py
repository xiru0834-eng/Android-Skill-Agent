import unittest
from startup_matrix import make_blocks, make_phone_blocks, make_failfast_blocks, summarize_policies, validate_policy


class StartupMatrixTest(unittest.TestCase):
    def test_minimal_ablation_has_normal_and_fault_cases(self):
        blocks=make_failfast_blocks()
        self.assertEqual([len(b['cases']) for b in blocks],[6,8])
        self.assertTrue(all(b['policy']=='C2' for b in blocks))
        self.assertEqual(summarize_policies([],blocks)['C2']['unrun'],14)

    def test_phone_challenges_include_saved_but_dirty(self):
        blocks=make_phone_blocks(challenge=True)
        self.assertEqual(sum(len(b['cases']) for b in blocks),16)
        self.assertEqual(blocks[0]['cases'],blocks[1]['cases'])
        self.assertEqual({c['condition'] for c in blocks[0]['cases']},
            {'delay','navdelay','drop','rollback','missing','duplicate','dirty','dirty-already-at-target'})

    def test_phone_control_is_separate_and_counterbalanced(self):
        blocks=make_phone_blocks()
        self.assertEqual(sum(len(b['cases']) for b in blocks),24)
        self.assertTrue(all(b['config']=='phone' for b in blocks))
        self.assertEqual([b['policy'] for b in blocks],['B0','C1','C1','B0'])
        self.assertEqual(blocks[0]['cases'],blocks[1]['cases'])
        self.assertEqual(blocks[2]['cases'],blocks[3]['cases'])

    def test_balanced_matched_counterbalanced(self):
        blocks = make_blocks()
        self.assertEqual(blocks, make_blocks())
        self.assertEqual(sum(len(b['cases']) for b in blocks), 72)
        for i in range(0, len(blocks), 2):
            a, b = blocks[i:i+2]
            self.assertEqual(a['config'], b['config'])
            self.assertEqual(a['cases'], b['cases'])
            self.assertEqual([a['policy'], b['policy']], ['B0','C1'] if a['repeat']==0 else ['C1','B0'])
        for policy in ('B0','C1'):
            self.assertEqual(sum(len(b['cases']) for b in blocks if b['policy']==policy), 36)

    def test_rejects_wrong_binary_result(self):
        validate_policy({'startupPolicy':'C1', 'deadlineMs':31000,'startedMs':1000},'C1')
        with self.assertRaises(ValueError):
            validate_policy({'startupPolicy':'B0', 'deadlineMs':31000,'startedMs':1000},'C1')
        with self.assertRaises(ValueError):
            validate_policy({'startupPolicy':'C1', 'deadlineMs':32000,'startedMs':1000},'C1')

    def test_missing_evidence_and_unrun_remain_visible(self):
        rows=[dict(config='compact', policy='C1', case={'initialId':'S0'}, evidence_complete=False)]
        s=summarize_policies(rows,make_blocks())
        self.assertEqual(s['overall']['unrun'],71)
        self.assertEqual(s['C1']['infrastructureFailures'],1)
        self.assertEqual(s['C1']['scored'],0)
        self.assertEqual(s['B0']['unrun'],36)


if __name__=='__main__':unittest.main()
