import json
import threading
import unittest
import urllib.request
import urllib.error
from intent_bridge import BridgeServer
from test_parameter_calls import CATALOG,result

class ParameterBridgeTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        def interpreter(text,catalog,budget):
            self.calls.append(text);budget.check();return result(percent=80)
        self.server=BridgeServer(('127.0.0.1',0),'x'*48,max_calls=2,parameter_interpreter=interpreter)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def post(self,body,path='parameter-calls',token='x'*48):
        req=urllib.request.Request('http://127.0.0.1:%s/v1/%s'%(self.server.server_port,path),data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token})
        try:
            with urllib.request.urlopen(req,timeout=3) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)
    def test_reject_auth_catalog_before_model(self):
        body=dict(request_id='a'*32,text='80%',skills=CATALOG)
        self.assertEqual(self.post(body,token='wrong')[0],401)
        body['skills']=[];self.assertEqual(self.post(body)[0],400);self.assertEqual(self.calls,[])
    def test_shared_cap_duplicate_echo_and_cancel(self):
        body=dict(request_id='a'*32,text='80%',skills=CATALOG)
        code,data=self.post(body);self.assertEqual(code,200);self.assertEqual(data['request_id'],body['request_id'])
        self.assertEqual(self.post(body)[0],409)
        body['request_id']='b'*32;self.post(dict(request_id=body['request_id']),'skill-selection-cancellations')
        self.assertEqual(self.post(body)[0],503);self.assertEqual(len(self.calls),1)
        body['request_id']='c'*32;self.assertEqual(self.post(body)[0],429)
    def test_invalid_model_never_returns_call(self):
        self.server.parameter_interpreter=lambda *args:result(percent=55)
        self.assertEqual(self.post(dict(request_id='a'*32,text='80%',skills=CATALOG))[0],502)

if __name__=='__main__':unittest.main()
