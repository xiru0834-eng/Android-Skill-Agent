"""Local HTTP integration faults; these are not remote availability samples."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from compiler import ModelError
from intent_bridge import BridgeServer
from jev_selection import select_jev
from test_jev_selection import response
from test_skill_selection import CATALOG


class JevBridgeFaultTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        def selector(text, skills):
            self.calls.append(text)
            return select_jev(text, skills, lambda _: response())
        self.server=BridgeServer(('127.0.0.1',0),'t'*40,max_calls=2,skill_selector=selector)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)

    def request(self, text='Run the skill', identity='a'*32, skills=None, token='t'*40, raw=None):
        body=dict(request_id=identity,text=text,skills=CATALOG if skills is None else skills)
        req=urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/v1/skill-selections',
            data=raw if raw is not None else json.dumps(body).encode(),headers={'Authorization':'Bearer '+token})
        try:
            with urllib.request.urlopen(req,timeout=3) as r: return r.status,json.load(r)
        except urllib.error.HTTPError as e: return e.code,json.load(e)

    def no_id(self, result, code):
        self.assertEqual(result[0],code); self.assertNotIn('skill_id',result[1]); self.assertNotIn('status',result[1])

    def test_unauthorized_invalid_catalog_and_duplicate_json_never_reach_selector(self):
        self.no_id(self.request(token='wrong'),401)
        self.no_id(self.request(skills=CATALOG+CATALOG[:1]),400)
        self.no_id(self.request(raw=b'{"request_id":"a","request_id":"b"}'),400)
        self.assertEqual(self.calls,[])

    def test_invalid_response_unknown_id_and_version_fail_closed(self):
        for index,kind in enumerate(('wrong-version','unknown-option')):
            def choose(*args):
                data=response()
                if kind=='wrong-version': data['model']='wrong'
                else: data['answers']['selection']['choice']='unregistered'
                return select_jev(args[0],args[1],lambda _: data)
            self.server.skill_selector=choose
            self.no_id(self.request(identity=str(index+1)*32),502)

    def test_network_or_quota_error_is_unavailable_not_successful_reject(self):
        for index,code in enumerate(('NETWORK_OR_TIMEOUT','HTTP_429')):
            def failure(*args): raise ModelError(code)
            self.server.skill_selector=failure
            result=self.request(identity=str(index+1)*32)
            self.no_id(result,503); self.assertEqual(result[1],dict(error=code))

    def test_low_confidence_is_null_clarify_not_invocation(self):
        self.server.skill_selector=lambda text,skills: select_jev(text,skills,lambda _: response(confidence=.89))
        code,body=self.request()
        self.assertEqual(code,200); self.assertEqual(body['status'],'clarify'); self.assertIsNone(body['skill_id'])

    def test_replay_and_call_cap_cannot_create_more_proposals(self):
        self.assertEqual(self.request()[0],200)
        self.no_id(self.request(),409)
        self.assertEqual(self.request(identity='b'*32)[0],200)
        self.no_id(self.request(identity='c'*32),429)
        self.assertEqual(len(self.calls),2)

    def test_busy_response_and_original_request_are_separate(self):
        entered=threading.Event(); release=threading.Event(); results=[]
        def blocking(text, skills):
            entered.set()
            if not release.wait(2): raise ModelError('TEST_TIMEOUT')
            return select_jev(text,skills,lambda _: response())
        self.server.skill_selector=blocking
        worker=threading.Thread(target=lambda: results.append(self.request()))
        worker.start()
        try:
            self.assertTrue(entered.wait(1)); self.no_id(self.request(identity='b'*32),409)
        finally: release.set(); worker.join(timeout=3)
        self.assertEqual(results[0][0],200)


if __name__ == '__main__': unittest.main()
