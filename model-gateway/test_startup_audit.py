import unittest
from startup_audit import paired, input_safety


class StartupAuditTest(unittest.TestCase):
    def row(self,policy,ok,ms=1000,initial='S0'):
        return dict(policy=policy,config='compact',case=dict(initialId=initial,repeat=0),
                    evidence_complete=True,confirmed_success=ok,elapsed_ms=ms)

    def test_pairs_by_condition_not_row_position(self):
        s=paired([self.row('C1',True,1300),self.row('B0',True,1000)])
        self.assertEqual(s['pairedTasks'],1);self.assertEqual(s['bothSuccess'],1)
        self.assertEqual(s['needsInputDeltaMedianMs'],300)

    def test_does_not_replace_failures_with_noops(self):
        rows=[self.row('B0',False),self.row('C1',True,1500),
              self.row('B0',True,1000,'S5'),self.row('C1',True,1100,'S5')]
        s=paired(rows);self.assertEqual(s['candidateOnlySuccess'],1)
        self.assertIsNone(s['needsInputDeltaMedianMs']);self.assertEqual(s['alreadyDeltaMedianMs'],100)

    def test_missing_and_duplicate(self):
        r=self.row('B0',True);s=paired([r]);self.assertEqual(s['unpairedTasks'],1)
        with self.assertRaises(ValueError):paired([r,r])

    def test_fault_conditions_do_not_collide(self):
        a=self.row('B0',False);b=self.row('B0',False)
        a['case']['condition']='dirty';b['case']['condition']='missing'
        self.assertEqual(paired([a,b])['unpairedTasks'],2)

    def test_counts_deadline_not_just_terminal_and_rejects_unknown_target(self):
        skill={'finalGoals':[1,60,1,1], 'steps':[{'id':'known'}]}
        oracle={'initial':[1,60,1,1], 'events':[{'ms':3000,'kind':'input:unknown'}]}
        result={'startedMs':0,'finishedMs':3100,'deadlineMs':3000}
        s=input_safety(oracle,result,skill)
        self.assertEqual(s['afterDeadlineInputs'],1)
        self.assertEqual(s['unexpectedIds'],1)
        self.assertEqual(s['extraInputs'],1)


if __name__=='__main__':unittest.main()
