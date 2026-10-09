import unittest
from recovery_replay import select_case


class ReplayTest(unittest.TestCase):
    def test_exact_predeclared_case_and_policy_are_selected(self):
        protocol={'blocks':[{'config':'phone','policy':'OFF','cases':[{'id':1}]},
                            {'config':'wide','policy':'R1','cases':[{'id':2},{'id':3}]}]}
        self.assertEqual(select_case(protocol,2),{'config':'wide','policy':'R1','cases':[{'id':3}]})
        for index in (-1,3,True):
            with self.assertRaises(ValueError):select_case(protocol,index)


if __name__=='__main__':unittest.main()
