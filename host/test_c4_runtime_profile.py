"""Versioned metadata contract only: never proof of a live device or execution."""
import copy,tempfile,unittest
from pathlib import Path
from c2_material import from_recording,canonical,digest
from test_c2_learning import payload,draft
from test_draft_generator import FakeModel,reply
from c2_learning import LearningService
import c2_runtime_request as current
from c2_runtime_abstraction import analyze
from learning_request import build_request as old_request

def context():
    return {'environment':copy.deepcopy(payload()['environment']),
        'probe_apk_sha256':current.PROBE107_SHA256,'app_version_code':'6','app_version_name':'0.8-parameter-room',
        'document':'Current compiled READ adapter; no UI identity or execution authority.', 'execution_authority':False}
def material():
    p=payload();return from_recording([],None,p['document'],p['environment'])

class RuntimeProfileTests(unittest.TestCase):
    def setUp(self):self.bundle=material()
    def snapshot(self,**kw):return current.capture_snapshot(context(),**kw)
    def request(self,snapshot=None):return current.build_request('Learn brightness',[self.bundle],runtime_snapshot=snapshot or self.snapshot())
    def test_old_contract_remains_unchanged(self):
        r=old_request('Learn brightness',[material()]);self.assertFalse(r['allowed_capabilities']['native_flow_read_adapter'])
        self.assertNotIn('runtime_capability_profile',r)
    def test_new_contract_exposes_static_read_not_identity_or_permission(self):
        r=self.request();p=r['runtime_capability_profile']
        self.assertTrue(r['allowed_capabilities']['native_flow_read_adapter'])
        self.assertEqual(p['identity_assurance'],'NOT_ESTABLISHED_BY_PROFILE')
        self.assertFalse(p['execution_authority']);self.assertFalse(r['execution_authority'])
        self.assertIn('ENTITY_MAPPING_UNCONFIRMED',r['knowledge_gaps'])
        self.assertIn('MATERIAL_UNKNOWNS_PRESENT',r['knowledge_gaps'])
        self.assertNotIn('BUILD_VERSION_RELATION_UNCONFIRMED',r['knowledge_gaps'])
    def test_wrong_apk_rejected(self):
        c=context();c['probe_apk_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'CURRENT_PROBE_PROFILE_MISMATCH'):current.capture_snapshot(c)
    def test_wrong_build_rejected(self):
        for field,value in [('app_version_code','7'),('app_version_name','fake')]:
            c=context();c[field]=value
            with self.assertRaises(ValueError):current.capture_snapshot(c)
    def test_extra_authority_or_hidden_map_rejected(self):
        for field,value in [('execution_authority',True),('hidden_locators',{})]:
            c=context();c[field]=value
            with self.assertRaises(ValueError):current.capture_snapshot(c)
    def test_client_json_is_not_runtime_snapshot(self):
        with self.assertRaisesRegex(ValueError,'TRUSTED_RUNTIME_SNAPSHOT_REQUIRED'):
            current.build_request('Learn brightness',[material()],runtime_snapshot=self.request()['runtime_capability_profile'])
    def test_profile_expiry(self):
        now=[0.0];s=self.snapshot(clock=lambda:now[0]);now[0]=120.001
        with self.assertRaisesRegex(ValueError,'RUNTIME_PROFILE_EXPIRED'):self.request(s)
    def test_clock_reversal(self):
        now=[10.0];s=self.snapshot(clock=lambda:now[0]);now[0]=9.9
        with self.assertRaisesRegex(ValueError,'RUNTIME_PROFILE_EXPIRED'):self.request(s)
    def test_wrong_environment_rejected(self):
        b=material();b['environment']['ui_revision']='ui.u1'
        with self.assertRaises(ValueError):current.build_request('Learn brightness',[b],runtime_snapshot=self.snapshot())
    def test_reconstruction_accepts_same_trusted_profile(self):
        s=self.snapshot();r=self.request(s)
        current.validate_request(r,[self.bundle],runtime_snapshot=s)
    def test_changed_materials_rejected_even_with_recomputed_digest(self):
        s=self.snapshot();r=self.request(s);r['material']['documents'][0]['text']='invented'
        r['input_digest']=digest({k:v for k,v in r.items() if k not in ('input_digest','request_id')})
        with self.assertRaisesRegex(ValueError,'MATERIAL_MISMATCH'):current.validate_request(r,[self.bundle],runtime_snapshot=s)
    def test_forged_capability_rejected_with_valid_digest(self):
        s=self.snapshot();r=self.request(s);r['allowed_capabilities']['entity_capabilities'][0]['entity_id']='forged'
        r['input_digest']=digest({k:v for k,v in r.items() if k not in ('input_digest','request_id')})
        with self.assertRaises(ValueError):current.validate_request(r,[self.bundle],runtime_snapshot=s)
    def test_profile_is_required_by_new_analyzer(self):
        r=self.request();a=analyze(r,canonical(draft()),[self.bundle],input_channel='FAKE_MODEL_PROTOCOL_ONLY')
        self.assertEqual(a['status'],'TRUSTED_RUNTIME_SNAPSHOT_REQUIRED')
    def test_analysis_uses_same_new_contract_and_keeps_unknowns(self):
        s=self.snapshot();r=self.request(s);a=analyze(r,canonical(draft()),[self.bundle],runtime_snapshot=s,input_channel='FAKE_MODEL_PROTOCOL_ONLY')
        self.assertEqual(a['status'],'ANALYZED_DRAFT_WITH_UNKNOWNS')
        self.assertFalse(a['ready_for_execution']);self.assertTrue(a['unknowns'])
    def test_service_default_remains_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            s=LearningService(tmp,test_mode=True,model=FakeModel([reply(draft())]),public_context=context)
            r=s.generate('a'*32,payload());self.assertFalse(r['body']['material']['request']['allowed_capabilities']['native_flow_read_adapter'])
    def test_enabled_service_requires_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'CURRENT_RUNTIME_PROVIDER_REQUIRED'):LearningService(tmp,runtime_profile_enabled=True)
    def test_enabled_service_generation_is_inert_and_profile_checked_twice(self):
        calls=[]
        def provider():calls.append(1);return context()
        with tempfile.TemporaryDirectory() as tmp:
            s=LearningService(tmp,test_mode=True,model=FakeModel([reply(draft())]),public_context=provider,runtime_profile_enabled=True)
            r=s.generate('b'*32,payload());self.assertEqual(len(calls),2)
            self.assertEqual(r['state'],'DRAFT');self.assertFalse(r['execution_authority'])
            self.assertTrue(r['body']['material']['request']['allowed_capabilities']['native_flow_read_adapter'])
    def test_revoked_provider_after_model_cannot_publish_candidate(self):
        calls=[]
        def provider():
            calls.append(1)
            if len(calls)>1:raise ValueError('LOCAL_PACKAGE_REVIEW_REQUIRED')
            return context()
        with tempfile.TemporaryDirectory() as tmp:
            s=LearningService(tmp,test_mode=True,model=FakeModel([reply(draft())]),public_context=provider,runtime_profile_enabled=True)
            with self.assertRaisesRegex(ValueError,'LOCAL_PACKAGE_REVIEW_REQUIRED'):s.generate('c'*32,payload())
            self.assertEqual(s.inbox.inspect('c'*32)['state'],'FAILED')
    def test_enabled_service_http_payload_cannot_supply_profile(self):
        with tempfile.TemporaryDirectory() as tmp:
            model=FakeModel([reply(draft())]);s=LearningService(tmp,test_mode=True,model=model,public_context=context,runtime_profile_enabled=True)
            p=payload();p['runtime_capability_profile']=self.request()['runtime_capability_profile']
            with self.assertRaises(ValueError):s.generate('d'*32,p)
            self.assertEqual(model.calls,[])
    def test_sanitized_goal_reconstructs_from_original_out_of_band(self):
        s=self.snapshot();goal='Learn brightness '+'sk-proj-'+'X'*40
        r=current.build_request(goal,[self.bundle],runtime_snapshot=s)
        self.assertNotIn('X'*40,canonical(r));self.assertTrue(r['goal_redaction_applied'])
        current.validate_request(r,[self.bundle],runtime_snapshot=s,original_goal=goal)
    def test_changed_runtime_after_model_cannot_complete(self):
        calls=[]
        def provider():
            calls.append(1);c=context()
            if len(calls)>1:c['probe_apk_sha256']='0'*64
            return c
        with tempfile.TemporaryDirectory() as tmp:
            s=LearningService(tmp,test_mode=True,model=FakeModel([reply(draft())]),public_context=provider,runtime_profile_enabled=True)
            with self.assertRaisesRegex(ValueError,'CURRENT_PROBE_PROFILE_MISMATCH'):s.generate('e'*32,payload())
            self.assertEqual(s.inbox.inspect('e'*32)['state'],'FAILED')
    def test_new_contract_cancel_does_not_resurrect(self):
        with tempfile.TemporaryDirectory() as tmp:
            m=FakeModel([reply(draft())]);s=LearningService(tmp,test_mode=True,model=m,public_context=context,runtime_profile_enabled=True)
            m.hook=lambda:s.cancel('f'*32)
            with self.assertRaises(ValueError):s.generate('f'*32,payload())
            self.assertEqual(s.inbox.inspect('f'*32)['state'],'CANCELLED')
    def test_provider_failure_before_generation_sends_nothing(self):
        def denied():raise ValueError('LOCAL_PACKAGE_REVIEW_REQUIRED')
        with tempfile.TemporaryDirectory() as tmp:
            m=FakeModel([reply(draft())]);s=LearningService(tmp,test_mode=True,model=m,public_context=denied,runtime_profile_enabled=True)
            with self.assertRaises(ValueError):s.generate('a'*32,payload())
            self.assertEqual(m.calls,[])
    def test_runtime_flag_rejects_strings(self):
        with tempfile.TemporaryDirectory() as tmp:
            for value in ('false',1,None):
                with self.assertRaises(ValueError):LearningService(tmp,runtime_profile_enabled=value)

if __name__=='__main__':unittest.main(verbosity=2)
