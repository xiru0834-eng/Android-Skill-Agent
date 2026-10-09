import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from intent_bridge import BridgeServer
from test_semantic_parameter_calls import CATALOG, invocation


class SemanticBridgeTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        def interpreter(text,catalog,budget):
            self.calls.append(text);budget.check();return invocation()
        self.server=BridgeServer(('127.0.0.1',0),'x'*48,max_calls=3,semantic_interpreter=interpreter)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
    def post(self,body,path='/v2/parameter-calls',token='x'*48):
        req=urllib.request.Request('http://127.0.0.1:%s%s'%(self.server.server_port,path),
            data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token})
        try:
            with urllib.request.urlopen(req,timeout=3) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    def body(self,char='a',text='Set desk lamp to 80 percent'):
        return dict(request_id=char*32,text=text,skills=CATALOG)
    def test_auth_invalid_catalog_and_text_do_not_call_model(self):
        self.assertEqual(self.post(self.body(),token='bad')[0],401)
        for data in [dict(self.body(),skills=[]),dict(self.body(),text='x'*2001),dict(self.body(),approved=True)]:
            self.assertEqual(self.post(data)[0],400)
        self.assertEqual(self.calls,[]);self.assertEqual(self.server.count,0)
    def test_success_echo_and_duplicate(self):
        code,data=self.post(self.body());self.assertEqual(code,200)
        self.assertEqual(data['request_id'],'a'*32)
        self.assertEqual(data['calls'],invocation()['calls'])
        self.assertEqual(self.post(self.body())[0],409);self.assertEqual(len(self.calls),1)
    def test_shared_cancel_before_admission_zero_model_work(self):
        self.assertEqual(self.post(dict(request_id='a'*32),'/v1/skill-selection-cancellations')[0],200)
        code,data=self.post(self.body());self.assertEqual(code,503)
        self.assertEqual(data,dict(error='SELECTION_CANCELLED'));self.assertEqual(self.calls,[])
    def test_invalid_last_call_does_not_return_partial_plan(self):
        def malformed(*args):
            data=invocation();data['calls'].append(invocation(device='unknown')['calls'][0]);return data
        self.server.semantic_interpreter=malformed
        code,data=self.post(self.body());self.assertEqual(code,502)
        self.assertNotIn('calls',data)
    def test_deadline_discards_late_result(self):
        self.server.selection_seconds=.06
        def late(text,catalog,budget):
            return budget.call(lambda body,timeout:(time.sleep(.15) or dict(draft=invocation())),{},'fake')['draft']
        self.server.semantic_interpreter=late
        code,data=self.post(self.body());self.assertEqual(code,503)
        self.assertEqual(data,dict(error='SELECTION_DEADLINE'))
    def test_session_cap_shared_with_v1_and_no_retry(self):
        from test_parameter_calls import CATALOG as OLD, result
        self.server.parameter_interpreter=lambda *args:result(percent=80)
        self.assertEqual(self.post(self.body('a'))[0],200)
        self.assertEqual(self.post(dict(request_id='b'*32,text='80%',skills=OLD),'/v1/parameter-calls')[0],200)
        self.assertEqual(self.post(self.body('c'))[0],200)
        self.assertEqual(self.post(self.body('d'))[0],429)
        self.assertEqual(self.server.count,3);self.assertEqual(len(self.calls),2)


if __name__=='__main__':unittest.main()
