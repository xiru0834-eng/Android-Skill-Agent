import unittest
from named_journey_device import wait_fixture

class FixtureReadyTests(unittest.TestCase):
    def test_waits_for_same_case_and_initial_without_reissuing_reset(self):
        rows=iter([{'caseId':'old','initial':[0,40,0,3]},{'caseId':'new','initial':[1,60,0,3]},{'caseId':'new','initial':[0,40,0,3]}]);clock=[0]
        result=wait_fixture(lambda:next(rows),'new',[0,40,0,3],clock=lambda:clock[0],sleep=lambda t:clock.__setitem__(0,clock[0]+t))
        self.assertEqual(result['initial'],[0,40,0,3]);self.assertGreater(clock[0],0)
    def test_never_accepts_previous_case(self):
        clock=[0]
        with self.assertRaises(RuntimeError):wait_fixture(lambda:dict(caseId='old',initial=[0,40,0,3]),'new',[0,40,0,3],clock=lambda:clock[0],sleep=lambda t:clock.__setitem__(0,clock[0]+t),timeout=.5)
