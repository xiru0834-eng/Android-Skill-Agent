import unittest
from test_workflow_contract import trace_fixture
from workflow_compile import build_request, compile_trace
from workflow_contract import WorkflowError

class CompileTests(unittest.TestCase):
    def test_remote_request_does_not_include_approval_or_tools(self):
        body=build_request(trace_fixture());self.assertFalse(body['store']);self.assertNotIn('tools',body)
    def test_verified_model_proposal_preserves_source(self):
        def fake(body):return dict(draft=dict(status='candidate',reason='Matches',indices=list(range(1,9))))
        result=compile_trace(trace_fixture(),fake)
        self.assertEqual(result['skill']['finalGoals'],[1,60,1,1]);self.assertEqual(result['reviewStatus'],'UNREVIEWED')
    def test_clarification_produces_no_skill(self):
        result=compile_trace(trace_fixture(),lambda _:dict(draft=dict(status='clarify',reason='Ambiguous goal',indices=[])))
        self.assertIsNone(result['skill'])
    def test_model_cannot_reorder_steps(self):
        with self.assertRaises(WorkflowError):compile_trace(trace_fixture(),lambda _:dict(draft=dict(status='candidate',reason='Changed',indices=list(range(8,0,-1)))))

if __name__=='__main__':unittest.main()
