import copy
import unittest
from workflow_contract import compile_evidence, validate_proposal, WorkflowError


def trace_fixture():
    def snap(page, values=None, saved=None):
        return dict(page=page, values=values or {}, saved=saved or [], dirty=False)
    initial=snap('overview',saved=[0,40,0,3]); steps=[]; before=initial
    for group, start, target, old in [('Lamp','lamp',60,40),('Fan','fan',1,3)]:
        vals={f'wf{group}Power':False,f'wf{group}Value{old}':True,f'wf{group}Value{target}':False}
        for key,after in [
            ('wfOpen'+group,snap(start,vals.copy())),
            ('wf'+group+'Power',snap(start,dict(vals,**{f'wf{group}Power':True}))),
            ('wf'+group+'Value'+str(target),snap(start,{f'wf{group}Power':True,f'wf{group}Value{old}':False,f'wf{group}Value{target}':True})),
            ('wf'+group+'Save',snap('overview',saved=[1,60,0,3] if group=='Lamp' else [1,60,1,1]))]:
            steps.append(dict(id=key,before=before,after=after,eventTime=len(steps)+1,attribution='RESOURCE_ID'))
            before=after
    return dict(kind='WORKFLOW_TRACE',version=1,traceId='12345678-1234-1234-1234-123456789abc',
                appPackage='edu.sydney.transferlab',appVersion='3',source='AUTOMATED',goal='Set the room',
                end='STOPPED',error='',initial=initial,steps=steps,final=before)


class WorkflowContractTests(unittest.TestCase):
    def test_complete_record_yields_evidence_bound_skill(self):
        skill=compile_evidence(trace_fixture())
        self.assertEqual(skill['finalGoals'],[1,60,1,1]);self.assertEqual(len(skill['steps']),8)
        self.assertNotIn('approved',skill)
    def test_incomplete_record_rejected(self):
        trace=trace_fixture();trace['steps'].pop(2)
        with self.assertRaises(WorkflowError):compile_evidence(trace)
    def test_recording_not_stopped_rejected(self):
        trace=trace_fixture();trace['end']='RECORDING'
        with self.assertRaises(WorkflowError):compile_evidence(trace)
    def test_foreign_package_rejected(self):
        trace=trace_fixture();trace['appPackage']='other.app'
        with self.assertRaises(WorkflowError):compile_evidence(trace)
    def test_final_goal_rollback_rejected(self):
        trace=trace_fixture();trace['final']=copy.deepcopy(trace['final']);trace['final']['saved'][0]=0
        with self.assertRaises(WorkflowError):compile_evidence(trace)
    def test_extra_action_rejected(self):
        trace=trace_fixture();trace['steps'][0]['id']='wfReset'
        with self.assertRaises(WorkflowError):compile_evidence(trace)
    def test_unknown_attribution_rejected(self):
        trace=trace_fixture();trace['steps'][0]['attribution']='GUESS'
        with self.assertRaises(WorkflowError):compile_evidence(trace)
    def test_model_may_not_remove_evidence_steps(self):
        with self.assertRaises(WorkflowError):validate_proposal(dict(status='candidate',reason='OK',indices=[1,2]),8)
    def test_model_acceptance_preserves_order(self):
        validate_proposal(dict(status='candidate',reason='Matches evidence',indices=list(range(1,9))),8)
    def test_boolean_is_not_numeric_goal(self):
        trace=trace_fixture();trace['steps'][-1]['after']['saved'][1]=True
        with self.assertRaises(WorkflowError):compile_evidence(trace)

if __name__=='__main__':unittest.main()
