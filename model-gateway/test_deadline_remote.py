import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from compiler import ModelError
from deadline_remote import post
from selection_deadline import SelectionBudget


class LocalHTTPTests(unittest.TestCase):
    def setUp(self):
        owner=self;self.requests=0;self.release=threading.Event();self.finished=threading.Event()
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                owner.requests+=1;self.rfile.read(int(self.headers['Content-Length']))
                if self.path=='/slow':owner.release.wait(2)
                if self.path=='/redirect':
                    self.send_response(302);self.send_header('Location','/echo');self.end_headers();return
                data=json.dumps(dict(value='dummy-sensitive-key')).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers()
                try:self.wfile.write(data)
                except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass
                finally:owner.finished.set()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.release.set();self.server.shutdown();self.server.server_close();self.thread.join(2)

    def test_echo_redaction_and_remaining_timeout_transport(self):
        self.assertEqual(post(self.url+'/echo',{},'dummy-sensitive-key',1),dict(value='[REDACTED]'))
        self.assertEqual(self.requests,1)

    def test_redirect_never_forwards_authorization(self):
        with self.assertRaisesRegex(ModelError,'HTTP_302'):post(self.url+'/redirect',{},'dummy-sensitive-key',1)
        self.assertEqual(self.requests,1)

    def test_cancel_while_real_http_is_blocked_discards_reply(self):
        stop=threading.Event();budget=SelectionBudget(1,cancelled=stop.is_set)
        timer=threading.Timer(.1,stop.set);timer.start();started=time.monotonic()
        try:
            with self.assertRaisesRegex(ModelError,'CANCELLED'):
                budget.call(lambda body,timeout:post(self.url+'/slow',body,'dummy-sensitive-key',timeout),{},'Jev')
            self.assertLess(time.monotonic()-started,.5)
            self.assertNotIn('response',budget.calls[0]);self.release.set();self.assertTrue(self.finished.wait(1))
            self.assertNotIn('response',budget.calls[0])
        finally:timer.cancel()

    def test_http_timeout_is_a_failure_not_rejection(self):
        with self.assertRaisesRegex(ModelError,'NETWORK_OR_TIMEOUT'):
            post(self.url+'/slow',{},'dummy-sensitive-key',.1)


if __name__=='__main__':unittest.main()
