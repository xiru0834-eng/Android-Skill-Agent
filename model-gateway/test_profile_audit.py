import copy
import unittest
from profile_audit import check_profile


class ProfileAuditTest(unittest.TestCase):
    def sample(self):
        p={name:dict(count=0,totalMs=0,maxMs=0) for name in ('SNAPSHOT','TARGET_LOOKUP','INPUT','JOURNAL')}
        p.update(SNAPSHOT=dict(count=1,totalMs=10,maxMs=10),INPUT=dict(count=1,totalMs=2,maxMs=2),
                 JOURNAL=dict(count=2,totalMs=3,maxMs=2))
        p['scope']='before this RESULT journal and result-file writes; non-overlapping measured sections only'
        return dict(profilePrefix=p,actions=[{}],startedMs=100,finishedMs=200),[{'kind':'START'},{'kind':'OBSERVATION'},{'kind':'RESULT'}]

    def test_valid_and_unmeasured_not_claimed_as_wait(self):
        r,j=self.sample();v=check_profile(r,j)
        self.assertEqual(v['measuredMs'],15)
        self.assertEqual(v['unattributedMs'],85)

    def test_reject_mismatched_action_or_prefix_counts(self):
        for part in ('INPUT','JOURNAL','SNAPSHOT'):
            r,j=self.sample();r['profilePrefix'][part]['count']=0
            with self.assertRaises(ValueError):check_profile(r,j)

    def test_reject_impossible_times(self):
        for field,value in [('totalMs',-1),('maxMs',11),('count',1.5),('count',True)]:
            r,j=self.sample();r['profilePrefix']['SNAPSHOT'][field]=value
            with self.assertRaises(ValueError):check_profile(r,j)
        r,j=self.sample();r['finishedMs']=114
        with self.assertRaises(ValueError):check_profile(r,j)

    def test_zero_count_requires_zero_time(self):
        r,j=self.sample();r['profilePrefix']['TARGET_LOOKUP']['totalMs']=1
        with self.assertRaises(ValueError):check_profile(r,j)

    def test_does_not_mutate_evidence(self):
        r,j=self.sample();before=copy.deepcopy((r,j));check_profile(r,j)
        self.assertEqual((r,j),before)


if __name__=='__main__':unittest.main()
