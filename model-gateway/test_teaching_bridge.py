import copy
import json
import threading
import unittest
import urllib.request
import urllib.error
from intent_bridge import BridgeServer
from test_workflow_contract import trace_fixture
from workflow_contract import compile_evidence


class TeachingBridgeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.status = 'candidate'
        def compile_trace(trace):
            self.calls.append(trace)
            return dict(status=self.status, reviewStatus='UNREVIEWED',
                        model=dict(draft=dict(reason='Reviewed evidence')),
                        skill=compile_evidence(trace) if self.status == 'candidate' else None)
        self.server = BridgeServer(('127.0.0.1', 0), 'x'*40,
                                   workflow_compiler=compile_trace, max_calls=2)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, trace=None, token='x'*40, request_id='a'*32, extra=None):
        body=dict(request_id=request_id, trace=trace if trace is not None else trace_fixture())
        body.update(extra or {})
        req=urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/v1/workflows',
            data=json.dumps(body).encode(), headers={'Authorization':'Bearer '+token})
        try:
            with urllib.request.urlopen(req, timeout=3) as r: return r.status,json.load(r)
        except urllib.error.HTTPError as e: return e.code,json.load(e)

    def test_candidate_remains_unreviewed_and_evidence_bound(self):
        code,result=self.request()
        self.assertEqual(code,200)
        self.assertEqual(result['skill'],compile_evidence(trace_fixture()))
        self.assertEqual(result['reviewStatus'],'UNREVIEWED')
        self.assertNotIn('model',result)

    def test_auth_and_bad_trace_do_not_spend_model_calls(self):
        self.assertEqual(self.request(token='wrong')[0],401)
        trace=trace_fixture();trace['end']='CANCELLED'
        self.assertEqual(self.request(trace)[0],400)
        self.assertEqual(self.request(extra={'approved':True})[0],400)
        self.assertEqual(self.calls,[])

    def test_clarify_and_reject_have_no_skill(self):
        for index,status in enumerate(['clarify','reject']):
            self.status=status
            code,result=self.request(request_id=str(index)*32)
            self.assertEqual(code,200);self.assertIsNone(result['skill'])

    def test_duplicates_and_session_limit(self):
        self.assertEqual(self.request()[0],200)
        self.assertEqual(self.request()[0],409)
        self.assertEqual(self.request(request_id='b'*32)[0],200)
        self.assertEqual(self.request(request_id='c'*32)[0],429)

    def test_compiler_cannot_substitute_another_skill(self):
        bad=compile_evidence(trace_fixture());bad['goal']='different'
        self.server.workflow_compiler=lambda trace:dict(status='candidate',reviewStatus='UNREVIEWED',
            model=dict(draft=dict(reason='Changed')),skill=bad)
        self.assertEqual(self.request()[0],502)


if __name__=='__main__': unittest.main()
