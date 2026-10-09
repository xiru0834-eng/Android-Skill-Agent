import copy
import unittest
from workflow_contract import compile_evidence, WorkflowError
from workflow_compile import build_request
from skill_selection import validate_catalog
from test_workflow_contract import trace_fixture

def single_trace(group='Lamp'):
    t=trace_fixture()
    if group=='Lamp':t['steps']=t['steps'][:4]
    else:
        t['steps']=t['steps'][4:];t['initial']=copy.deepcopy(t['steps'][0]['before'])
    t['final']=t['steps'][-1]['after'];return t

class PartialWorkflowTests(unittest.TestCase):
    def test_lamp_does_not_capture_demonstration_fan(self):
        s=compile_evidence(single_trace());self.assertEqual(s['version'],2)
        self.assertEqual(s['finalGoals'],[1,60,None,None]);self.assertEqual(len(s['steps']),4)
    def test_fan_does_not_capture_demonstration_lamp(self):
        self.assertEqual(compile_evidence(single_trace('Fan'))['finalGoals'],[None,None,1,1])
    def test_full_remains_v1(self):
        s=compile_evidence(trace_fixture());self.assertEqual(s['version'],1);self.assertEqual(s['finalGoals'],[1,60,1,1])
    def test_untouched_device_change_rejected(self):
        t=single_trace();t['final']['saved'][2]=1
        with self.assertRaises(WorkflowError):compile_evidence(t)
    def test_partial_block_not_accepted(self):
        for n in [0,1,2,3,5,6,7]:
            t=trace_fixture();t['steps']=t['steps'][:n]
            with self.assertRaises(WorkflowError):compile_evidence(t)
    def test_model_review_enumerates_only_observed_steps(self):
        r=build_request(single_trace());self.assertEqual(r['text']['format']['schema']['properties']['indices']['items']['enum'],[1,2,3,4])
    def test_catalog_partial_scope(self):
        for goals in [[1,60,None,None],[None,None,0,2]]:
            validate_catalog([dict(id='a'*64,name='Only',goal='Only one device',finalGoals=goals)])
    def test_catalog_invalid_scope(self):
        for goals in [[None]*4,[1,None,None,None],[None,None,1,None],[True,60,None,None],[1,61,None,None]]:
            with self.assertRaises(ValueError):validate_catalog([dict(id='a'*64,name='Only',goal='Only',finalGoals=goals)])
