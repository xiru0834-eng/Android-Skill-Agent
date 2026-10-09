"""Injector proof tests. No device call is made by these cases."""
import unittest
import xml.etree.ElementTree as ET
from task3_fault_device import triggered


class TriggerTests(unittest.TestCase):
    def test_parameter_alone_never_proves_dropped_save_or_rollback(self):
        before=dict(fault='drop',initial=[0,40,0,3],events=[dict(page='overview')])
        oracle=dict(events=[dict(kind='initial',saved=[0,40,0,3])]);result=dict(reason='STEP_UNCONFIRMED',finishedMs=100)
        self.assertFalse(triggered('save_drop',before,result,oracle,None,False))
        self.assertFalse(triggered('rollback',before,result,oracle,None,False))
        oracle['events'].append(dict(kind='dropped_save',saved=[0,40,0,3]))
        self.assertTrue(triggered('save_drop',before,result,oracle,None,False))
    def test_actual_duplicate_and_late_availability_are_required(self):
        before=dict(fault='duplicate');result=dict(finishedMs=100);oracle=dict(events=[])
        ui=ET.fromstring('<hierarchy><node resource-id="edu.sydney.transferlab:id/wfLampPower"/></hierarchy>')
        self.assertFalse(triggered('duplicate',before,result,oracle,ui,False))
        ET.SubElement(ui,'node',{'resource-id':'edu.sydney.transferlab:id/wfLampPower'})
        self.assertTrue(triggered('duplicate',before,result,oracle,ui,False))
        oracle['events']=[dict(kind='control_loading',ms=10),dict(kind='control_available',ms=99)]
        self.assertFalse(triggered('late',before,result,oracle,None,False))
        oracle['events'][-1]['ms']=101
        self.assertTrue(triggered('late',before,result,oracle,None,False))
    def test_intervention_without_proof_is_not_triggered(self):
        for fault in ['cancel','foreground']:
            with self.subTest(fault=fault):
                self.assertFalse(triggered(fault,{},dict(),dict(events=[]),None,False))


if __name__=='__main__':unittest.main()
