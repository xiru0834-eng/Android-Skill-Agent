import json
import threading
import unittest
import urllib.request
import urllib.error
from intent_bridge import BridgeServer


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        def interpret(text):
            self.calls.append(text)
            return dict(status='invoke',skill_id='room_controls',lamp=True,fan=None,message='OK')
        self.server = BridgeServer(('127.0.0.1',0), 'x'*40, interpret, max_calls=2)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

    def request(self, body, token='x'*40):
        req = urllib.request.Request('http://127.0.0.1:%s/v1/intents'%self.server.server_port,
            data=json.dumps(body).encode(), headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=2) as reply: return reply.status,json.load(reply)
        except urllib.error.HTTPError as error: return error.code,json.load(error)

    def test_auth_and_validation_do_not_call_model(self):
        self.assertEqual(self.request(dict(request_id='a'*32,text='开灯'),'wrong')[0],401)
        self.assertEqual(self.request(dict(request_id='a'*32,text=''))[0],400)
        self.assertEqual(self.calls, [])

    def test_request_id_echo_replay_and_budget(self):
        body=dict(request_id='a'*32,text='开灯')
        status,result=self.request(body)
        self.assertEqual(status,200); self.assertEqual(result['request_id'],body['request_id'])
        self.assertEqual(self.request(body)[0],409)
        self.assertEqual(self.request(dict(request_id='b'*32,text='Turn on the light'))[0],200)
        self.assertEqual(self.request(dict(request_id='c'*32,text='开灯'))[0],429)
        self.assertEqual(len(self.calls),2)


if __name__ == '__main__': unittest.main()
