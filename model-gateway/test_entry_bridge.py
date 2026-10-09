import json
import threading
import time
import unittest
import urllib.request
import urllib.error
from compiler import ModelError
from intent_bridge import BridgeServer
from test_skill_selection import CATALOG

class EntryBridgeTests(unittest.TestCase):
    def setUp(self):
        self.entered=threading.Event();self.release=threading.Event();self.calls=[]
        def selector(text,skills):
            self.calls.append(text);self.entered.set();self.release.wait(2)
            return dict(status='invoke',skill_id=skills[0]['id'],message='Review')
        self.server=BridgeServer(('127.0.0.1',0),'x'*48,max_calls=3,skill_selector=selector,selection_seconds=.3)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.release.set();self.server.shutdown();self.server.server_close();self.thread.join()
    def request(self,path,body,token='x'*48):
        req=urllib.request.Request(f'http://127.0.0.1:{self.server.server_port}/v1/'+path,
            data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token})
        try:
            with urllib.request.urlopen(req,timeout=3) as r:return r.status,json.load(r)
        except urllib.error.HTTPError as e:return e.code,json.load(e)
    def select(self,identity='a'*32):
        return self.request('skill-selections',dict(request_id=identity,text='Run saved skill.',skills=CATALOG))
    def cancel(self,identity='a'*32,token='x'*48):
        return self.request('skill-selection-cancellations',dict(request_id=identity),token)
    def test_cancel_does_not_wait_for_business_lock_and_no_late_delivery(self):
        result=[];worker=threading.Thread(target=lambda:result.append(self.select()));worker.start()
        self.assertTrue(self.entered.wait(1));start=time.monotonic()
        self.assertEqual(self.cancel()[0],200);self.assertLess(time.monotonic()-start,.2)
        worker.join(1);self.assertFalse(worker.is_alive())
        self.assertEqual(result[0],(503,dict(error='SELECTION_CANCELLED')))
        self.release.set()
    def test_cancel_can_arrive_first_and_is_idempotent(self):
        self.assertEqual(self.cancel(),(200,dict(request_id='a'*32,status='cancelled')))
        self.assertEqual(self.cancel()[0],200)
        self.assertEqual(self.select(),(503,dict(error='SELECTION_CANCELLED')))
        self.assertEqual(self.calls,[])
    def test_wrong_auth_invalid_body_and_cancellation_capacity(self):
        self.assertEqual(self.cancel(token='bad')[0],401)
        self.assertEqual(self.cancel(identity='bad')[0],400)
        self.assertEqual(self.request('skill-selection-cancellations',dict(request_id='a'*32,skill_id='x'))[0],400)
        for c in 'abc':self.assertEqual(self.cancel(c*32)[0],200)
        self.assertEqual(self.cancel('d'*32)[0],429)
        self.assertEqual(self.cancel('a'*32)[0],200)
        self.assertEqual(self.calls,[])
    def test_server_deadline_rejects_late_correct_result(self):
        started=time.monotonic();code,reply=self.select()
        self.assertEqual((code,reply),(503,dict(error='SELECTION_DEADLINE')))
        self.assertLess(time.monotonic()-started,1)
        self.release.set()
    def test_cancelled_previous_request_does_not_cancel_new_request(self):
        self.cancel();self.release.set()
        code,reply=self.select('b'*32)
        self.assertEqual(code,200);self.assertEqual(reply['skill_id'],'a'*64)
    def test_bounded_selector_receives_shared_budget(self):
        budgets=[]
        def choose(text,skills,budget):
            budgets.append(budget);budget.check()
            return dict(status='reject',skill_id=None,message='No')
        self.server.bounded_selector=choose
        self.assertEqual(self.select()[0],200)
        self.assertLessEqual(budgets[0].check(),.3)

    def test_active_request_can_be_cancelled_when_unknown_tombstones_are_full(self):
        for c in 'abc':self.assertEqual(self.cancel(c*32)[0],200)
        result=[];worker=threading.Thread(target=lambda:result.append(self.select('d'*32)))
        worker.start()
        try:
            self.assertTrue(self.entered.wait(1))
            self.assertEqual(self.cancel('d'*32),(200,dict(request_id='d'*32,status='cancelled')))
            worker.join(1);self.assertFalse(worker.is_alive())
            self.assertEqual(result,[(503,dict(error='SELECTION_CANCELLED'))])
            self.assertTrue(self.server.selection_events['d'*32].is_set())
            self.assertEqual(len(self.server.cancelled_ids),3,'unknown-ID storage must stay bounded')
            self.assertEqual(self.cancel('e'*32)[0],429)
            self.assertEqual(self.cancel('d'*32)[0],200,'known cancellation remains idempotent')
        finally:
            self.release.set();worker.join(2)

    def test_full_tombstone_set_does_not_grant_unauthenticated_known_cancellation(self):
        for c in 'abc':self.assertEqual(self.cancel(c*32)[0],200)
        result=[];worker=threading.Thread(target=lambda:result.append(self.select('d'*32)))
        worker.start()
        try:
            self.assertTrue(self.entered.wait(1))
            self.assertEqual(self.cancel('d'*32,token='bad')[0],401)
            self.assertFalse(self.server.selection_events['d'*32].is_set())
            self.release.set();worker.join(1)
            self.assertFalse(worker.is_alive());self.assertEqual(result[0][0],200)
        finally:
            self.release.set();worker.join(2)

    def test_deadline_does_not_retry_same_id_and_next_id_can_recover(self):
        self.assertEqual(self.select(),(503,dict(error='SELECTION_DEADLINE')))
        self.assertEqual(self.select(),(409,dict(error='DUPLICATE_REQUEST')))
        self.assertEqual(len(self.calls),1,'same ID must not retry a timed-out provider')
        self.release.set()
        code,reply=self.select('b'*32)
        self.assertEqual(code,200);self.assertEqual(reply['skill_id'],'a'*64)
        self.assertEqual(self.server.count,2)
        self.assertEqual([a['outcome'] for a in self.server.selection_audit],['SELECTION_DEADLINE','invoke'])

    def test_busy_request_does_not_consume_budget_or_call_model(self):
        result=[];worker=threading.Thread(target=lambda:result.append(self.select()))
        worker.start()
        try:
            self.assertTrue(self.entered.wait(1))
            self.assertEqual(self.select('b'*32),(409,dict(error='BUSY')))
            self.assertEqual(self.server.count,1);self.assertEqual(len(self.calls),1)
            self.assertEqual(self.cancel()[0],200)
            worker.join(1);self.assertEqual(result,[(503,dict(error='SELECTION_CANCELLED'))])
            self.release.set()
            self.assertEqual(self.select('b'*32)[0],200)
            self.assertEqual(self.server.count,2)
        finally:
            self.release.set();worker.join(2)

if __name__=='__main__':unittest.main()
