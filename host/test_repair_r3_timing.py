import unittest
from repair_r3_timing import union_length,stats

class TimingTest(unittest.TestCase):
    def test_overlap_is_not_double_counted(self): self.assertEqual(union_length([(0,5),(3,8),(10,12)]),10)
    def test_nested_is_not_double_counted(self): self.assertEqual(union_length([(0,10),(2,4)]),10)
    def test_empty(self): self.assertEqual(union_length([]),0)
    def test_invalid_clock(self):
        with self.assertRaises(ValueError): union_length([(2,1)])
    def test_no_denominator_is_not_zero(self): self.assertIsNone(stats([])['p50'])
    def test_nearest_rank(self): self.assertEqual(stats([1,2,3,4,5,6])['p95_nearest_rank'],6)

if __name__=='__main__': unittest.main()
