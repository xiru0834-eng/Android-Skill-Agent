"""Offline C2 orchestration; fake model channel is explicit, never device proof."""
import copy,json,tempfile,threading,unittest
from pathlib import Path
from c2_learning import LearningService
from c2_material import from_recording
from learning_request import build_request
from test_draft_generator import FakeModel,reply,response

ENV={'app_package':'edu.sydney.parameterroom','app_build':'6','environment_id':'parameter-room-u0','ui_revision':'ui.u0','domain':'EXPERIMENT_APP'}
def payload():return dict(goal='Learn brightness without changing power',environment=ENV,observations=[],legacy_trace=None,document='Public description of brightness adjustment',events=None,upload_confirmed=True)
def draft():return response(build_request(payload()['goal'],[from_recording([],None,payload()['document'],ENV)]))

class LearningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
    def service(self,values,hook=None,**kw):
        return LearningService(self.tmp.name,test_mode=True,model=FakeModel([reply(v) for v in values],hook),**kw)
    def test_generate_stays_draft_and_retains_unknowns(self):
        s=self.service([draft()]);r=s.generate('a'*32,payload())
        self.assertEqual(r['state'],'DRAFT');self.assertFalse(r['execution_authority'])
        self.assertFalse(r['body']['generation']['ready_for_device_execution']);self.assertTrue(r['body']['generation']['knowledge_gaps'])
        self.assertEqual(r['body']['generation']['evidence_channel'],'FAKE_MODEL_PROTOCOL_ONLY')
    def test_missing_read_dependency_normalized_without_business_calls(self):
        d=draft()
        for i in d['candidate_flow']['inputs']:
            if i['type']=='entity':i['required_capabilities'].remove('SetPower')
        d['candidate_flow']['dependencies']['capabilities'].remove('SetPower')
        s=self.service([d,copy.deepcopy(d)]);r=s.generate('a'*32,payload())
        n=r['body']['generation']['program_normalization'];self.assertTrue(n['diff'])
        self.assertEqual(n['flow']['steps'],d['candidate_flow']['steps'])
        self.assertEqual(r['body']['generation']['calls'],2)
        self.assertEqual(len(list((Path(self.tmp.name)/'audits').rglob('*response.json'))),2)
    def test_no_upload_consent_no_model(self):
        s=self.service([draft()]);p=payload();p['upload_confirmed']=False
        with self.assertRaises(ValueError):s.generate('a'*32,p)
        self.assertEqual(s.model.calls,[])
    def test_cancel_in_model_callback_does_not_resurrect(self):
        s=self.service([draft()]);s.model.hook=lambda:s.cancel('a'*32)
        with self.assertRaises(ValueError):s.generate('a'*32,payload())
        self.assertEqual(s.inbox.inspect('a'*32)['state'],'CANCELLED')
    def test_budget_survives_new_service(self):
        s=self.service([draft(),draft()]);s.generate('a'*32,payload());s.generate('b'*32,payload())
        restarted=self.service([draft()])
        with self.assertRaisesRegex(ValueError,'MODEL_LIMIT'):restarted.generate('c'*32,payload())
        self.assertEqual(restarted.model.calls,[])
    def test_duplicate_request_never_calls_model_again(self):
        s=self.service([draft()]);s.generate('a'*32,payload())
        with self.assertRaises(ValueError):s.generate('a'*32,payload())
        self.assertEqual(len(s.model.calls),1)
    def test_fabricated_authority_rejected(self):
        d=draft();d['execution_authority']=True;s=self.service([d,copy.deepcopy(d)])
        with self.assertRaises(ValueError):s.generate('a'*32,payload())
        self.assertEqual(s.inbox.inspect('a'*32)['state'],'FAILED')
    def test_unknown_capability_not_repaired(self):
        d=draft();d['candidate_flow']['steps'][2]['capability']='InventedAction';s=self.service([d,copy.deepcopy(d)])
        with self.assertRaises(ValueError):s.generate('a'*32,payload())
        self.assertEqual(s.inbox.inspect('a'*32)['state'],'FAILED')
    def test_serial_admission_different_ids(self):
        entered=threading.Event();release=threading.Event()
        s=self.service([draft(),draft()],hook=lambda:(entered.set(),release.wait(2)))
        errors=[]
        def first():
            try:s.generate('a'*32,payload())
            except Exception as e:errors.append(e)
        t=threading.Thread(target=first);t.start();self.assertTrue(entered.wait(2))
        try:
            with self.assertRaisesRegex(ValueError,'LEARNING_BUSY'):s.generate('b'*32,payload())
        finally:release.set();t.join(5)
        self.assertFalse(errors);self.assertEqual(len(s.model.calls),1)
    def test_first_normalizable_draft_not_lost_by_bad_format_repair(self):
        d=draft()
        for i in d['candidate_flow']['inputs']:
            if i['type']=='entity':i['required_capabilities'].remove('SetPower')
        d['candidate_flow']['dependencies']['capabilities'].remove('SetPower')
        broken=copy.deepcopy(d);del broken['candidate_flow']['dependencies']
        s=self.service([d,broken]);r=s.generate('a'*32,payload())
        g=r['body']['generation'];self.assertEqual(g['selected_raw_attempt'],1)
        self.assertEqual(g['candidate_flow']['steps'],d['candidate_flow']['steps'])
        self.assertEqual(g['calls'],2);self.assertFalse(g['ready_for_device_execution'])
    def test_valid_knowledge_gap_preserved_for_user_not_generic_failure(self):
        from test_draft_generator import request
        d=response(request(),gap=True)
        d['uncertainties'][0]['source_ids']=['user.document']
        s=self.service([d]);r=s.generate('a'*32,payload())
        self.assertEqual(r['state'],'NEEDS_MATERIAL');self.assertTrue(r['body']['generation']['questions'])
        with self.assertRaisesRegex(ValueError,'NOT_A_DRAFT'):s.inbox.name('a'*32,'not publishable')

if __name__=='__main__':unittest.main(verbosity=2)
