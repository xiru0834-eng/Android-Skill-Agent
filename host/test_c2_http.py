"""Actual loopback HTTP with fake-model protocol only, no ADB or external API."""
import http.client,json,tempfile,threading,unittest
from pathlib import Path
from c2_bridge import LearningServer,LearningService

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.server=LearningServer(('127.0.0.1',0),'a'*48,LearningService(Path(self.tmp.name)/'learning'))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close)
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(2)
    def send(self,value,headers=None):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            c.request('POST','/v3/learning',value if type(value) is str else json.dumps(value),headers=headers or {'Authorization':'Bearer '+'a'*48,'Content-Type':'application/json'})
            r=c.getresponse();return r.status,json.loads(r.read())
        finally:c.close()
    def body(self,op='status',payload=None):return dict(request_id='a'*32,operation=op,payload={} if payload is None else payload)
    def test_status_does_not_probe_paid_model(self):
        code,r=self.send(self.body());self.assertEqual(code,200)
        self.assertEqual(r['result']['model_api_usable'],'NOT_PROBED');self.assertFalse(r['execution_authority'])
    def test_unpaired_rejected(self):self.assertEqual(self.send(self.body(),{'Authorization':'Bearer bad','Content-Type':'application/json'})[0],401)
    def test_non_json_type_rejected(self):self.assertEqual(self.send(self.body(),{'Authorization':'Bearer '+'a'*48,'Content-Type':'text/plain'})[0],400)
    def test_execution_endpoint_not_exposed(self):
        c=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        try:
            c.request('POST','/v3/flow-tasks','{}',{'Authorization':'Bearer '+'a'*48,'Content-Type':'application/json'})
            r=c.getresponse();self.assertEqual(r.status,404);r.read()
        finally:c.close()
    def test_origin_rejected(self):self.assertEqual(self.send(self.body(),{'Authorization':'Bearer '+'a'*48,'Content-Type':'application/json','Origin':'https://untrusted.test'})[0],400)
    def test_duplicate_json_field_rejected(self):
        code,r=self.send('{"request_id":"'+'a'*32+'","operation":"status","payload":{},"operation":"generate"}')
        self.assertEqual(code,422);self.assertEqual(r['error'],'DUPLICATE_FIELD')
    def test_unknown_operation_cannot_publish(self):self.assertEqual(self.send(self.body('publish'))[0],422)
    def test_unknown_fields_rejected(self):
        b=self.body();b['approved']=True;self.assertEqual(self.send(b)[0],422)
    def test_file_path_not_identifier(self):
        b=self.body();b['request_id']='C:/private.json';self.assertEqual(self.send(b)[0],422)
    def test_missing_consent_stops_before_model(self):self.assertEqual(self.send(self.body('generate',{'upload_confirmed':False}))[0],422)
    def test_empty_inspect_does_not_read_device(self):self.assertEqual(self.send(self.body('inspect'))[0],422)
    def test_cancel_before_generation_tombstone(self):
        code,r=self.send(self.body('cancel'));self.assertEqual(code,200);self.assertEqual(r['result']['state'],'CANCELLED')
        with self.assertRaises(ValueError):self.server.learning.inbox.begin('a'*32,{})
    def test_finish_accepts_only_attempt_id_not_json_evidence(self):
        from unittest.mock import Mock
        c=Mock();self.server.learning.candidates=c
        self.assertEqual(self.send(self.body('finish_validation',{'attempt_id':'b'*32,'receipt':{'final_status':'SUCCESS'}}))[0],422)
        c.finish.assert_not_called()
    def test_lifecycle_routes_only_fixed_methods(self):
        from unittest.mock import Mock
        c=Mock();c.details.return_value={'execution_authority':False};self.server.learning.candidates=c
        code,r=self.send(self.body('candidate_details'));self.assertEqual(code,200)
        c.details.assert_called_once_with('a'*32);self.assertFalse(r['execution_authority'])
    def test_generation_busy_blocks_lifecycle(self):
        from unittest.mock import Mock
        c=Mock();self.server.learning.candidates=c;self.server.learning.active='b'*32
        self.assertEqual(self.send(self.body('prepare_validation',{'inputs':{}}))[0],422)
        c.prepare.assert_not_called()
    def test_client_cannot_choose_receipt_host_or_path(self):
        from unittest.mock import Mock
        c=Mock();self.server.learning.candidates=c
        for field in ('host','path','approved'):
            self.assertEqual(self.send(self.body('finish_validation',{'attempt_id':'b'*32,field:'foreign'}))[0],422)
        c.finish.assert_not_called()

if __name__=='__main__':unittest.main(verbosity=2)
