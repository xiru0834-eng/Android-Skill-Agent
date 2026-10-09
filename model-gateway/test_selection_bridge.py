import json
import threading
import unittest
import urllib.request
import urllib.error
from intent_bridge import BridgeServer
from test_skill_selection import CATALOG

class SelectionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        def choose(text,skills):
            self.calls.append(text)
            return dict(status='invoke',skill_id=skills[0]['id'],message='Review')
        self.server=BridgeServer(('127.0.0.1',0),'x'*40,max_calls=2,skill_selector=choose)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,body,token='x'*40):
        req=urllib.request.Request('http://127.0.0.1:%s/v1/skill-selections'%self.server.server_port,
            data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token})
        try:
            with urllib.request.urlopen(req,timeout=2) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def test_auth_validation_and_no_remote(self):
        body=dict(request_id='a'*32,text='read',skills=CATALOG)
        self.assertEqual(self.request(body,'wrong')[0],401)
        body['skills']=[];self.assertEqual(self.request(body)[0],400);self.assertEqual(self.calls,[])
    def test_id_echo_replay_cap(self):
        body=dict(request_id='a'*32,text='read',skills=CATALOG)
        code,result=self.request(body);self.assertEqual(code,200);self.assertEqual(result['request_id'],body['request_id'])
        self.assertEqual(self.request(body)[0],409)
        body['request_id']='b'*32;self.assertEqual(self.request(body)[0],200)
        body['request_id']='c'*32;self.assertEqual(self.request(body)[0],429)
    def test_invalid_model_fails_closed(self):
        self.server.skill_selector=lambda *a:dict(status='invoke',skill_id='unknown',message='')
        self.assertEqual(self.request(dict(request_id='a'*32,text='read',skills=CATALOG))[0],502)

if __name__=='__main__':unittest.main()
