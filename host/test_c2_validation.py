"""Synthetic native receipts / pure lifecycle only, never Android or paid-model evidence."""
import copy,json,tempfile,unittest
from pathlib import Path
from c2_inbox import DraftInbox
from c2_material import canonical,digest
from c2_validation import CandidateService,checked_receipt
from device_deps import compiler
from fixtures import bundle

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.inbox=DraftInbox(self.root/'inbox.sqlite')
        self.flow,self.package,self.task=bundle('SetBrightness',60)
        self.id='a'*32
        self.inbox.begin(self.id,{'bundle':{'sources':[]}})
        self.inbox.complete(self.id,{'candidate_flow':self.flow,'evidence_channel':'REAL_OPENAI_API','execution_authority':False})
        self.service=CandidateService(self.root/'lifecycle',self.inbox,'host.test',self.package)
        self.plan=compiler.compile_flow(self.flow,self.package,self.task,None).to_dict()
    def receipt(self):
        start={k:('off' if c['skill']=='SetPower' else c['domain']['min']) for k,c in self.plan['state_contracts'].items()}
        end=dict(start,**{'bedroom_light.brightnessPercent':60})
        def call(s):return {'skill':s['skill'],'args':{'device':s['entity_id'],s['argument']:s['value']['value']}}
        phases=['ENTRY']
        for s in self.plan['steps']:
            phases.append(s['id'])
            if s['op']=='CALL':phases.append('AFTER.'+s['id'])
        phases.append('FINAL');changed=False;observations=[]
        for i,phase in enumerate(phases,1):
            if phase.startswith('AFTER.'):changed=True
            observations.append(dict(phase=phase,values=copy.deepcopy(end if changed else start),kind='semantic_state_read_v1',channel='ANDROID_NATIVE',task_id=self.plan['task_id'],host_device_id=self.plan['host_device_id'],environment_hash=self.plan['environment_hash'],observation_session_id='read.session',sequence=i,captured_elapsed_ms=i,complete=True))
        return dict(request_id='b'*32,candidate_id=self.id,plan_raw_hash=digest(self.plan),native_plan_raw=canonical(self.plan),
            flow_plan_hash=digest(self.plan),task_id=self.plan['task_id'],host_device_id=self.plan['host_device_id'],
            transport_channel='NORMAL_USER_CANDIDATE_UI',channel='ANDROID_NATIVE',mode='CANDIDATE_VALIDATION',
            service_entry_hit=True,flow_hash=self.plan['flow_hash'],package_hash=self.plan['source_package_raw_hash'],
            final_status='SUCCESS',verification_result=True,completed_steps=len(self.plan['steps']),
            final_observation_complete=True,process_session='native.session',
            initial_state=start,final_observed_state=end,
            observations=observations,execution_actions=[dict(property='bedroom_light.brightnessPercent',value=60,method='SET_PROGRESS',effect_verified=True,effect_observation_complete=True,effect_observed_state=end)],
            event_scope_after={'sdk_available':True,'active':False,'original_filter_restored':True},
            completion_boundary={'stage':'SERVICE_RECEIPT_READY','final_status':'SUCCESS','finished_ms':100,'deadline_ms':8000},
            steps=[dict(op=s['op'],id=s['id'],status='VERIFIED',**({'runtime_receipt':{'calls':[call(s)],'verification_result':True,'final_status':'SUCCESS','final_observation_complete':True,'final_observed_state':end,'execution_actions':[dict(property=s['target_key'],value=60,method='SET_PROGRESS',effect_verified=True,effect_observation_complete=True,effect_observed_state=end)]}} if s['op']=='CALL' else {})) for s in self.plan['steps']])
    def test_prepare_is_inert_and_preserves_flow(self):
        r=self.service.prepare(self.id,self.task['inputs'])
        self.assertFalse(r['execution_authority']);self.assertEqual(r['flow_hash'],digest(self.flow))
        self.assertEqual(r['plan']['whole_budget_limit_ms'],8000)
        self.assertEqual(self.inbox.inspect(self.id)['state'],'DRAFT')
    def test_fake_model_cannot_prepare(self):
        bad='c'*32;self.inbox.begin(bad,{})
        self.inbox.complete(bad,{'candidate_flow':self.flow,'evidence_channel':'FAKE_MODEL_PROTOCOL_ONLY'})
        with self.assertRaisesRegex(ValueError,'REAL_MODEL_ORIGIN_REQUIRED'):self.service.prepare(bad,self.task['inputs'])
    def test_unresolved_unknown_cannot_prepare(self):
        bad='c'*32;self.inbox.begin(bad,{})
        f=copy.deepcopy(self.flow);f['unknowns'].append({'id':'missing','description':'unknown','impact':'BLOCKS_EXECUTION'})
        self.inbox.complete(bad,{'candidate_flow':f,'evidence_channel':'REAL_OPENAI_API'})
        with self.assertRaises(ValueError):self.service.prepare(bad,self.task['inputs'])
    def test_json_success_cannot_be_submitted(self):
        with self.assertRaisesRegex(ValueError,'TRUSTED_RECEIPT_READER_REQUIRED'):self.service.finish(self.id,'b'*32)
    def test_publish_requires_setting_evidence_and_name(self):
        self.service.prepare(self.id,self.task['inputs'])
        with self.assertRaises(ValueError):self.service.publish(self.id,confirmed=True)
    def test_bad_inputs_rejected_before_attempt(self):
        for values in ({},dict(self.task['inputs'],extra=1),dict(self.task['inputs'],value=101)):
            with self.assertRaises(ValueError):self.service.prepare(self.id,values)
    def test_receipt_requires_exact_identity(self):
        r=self.receipt()
        for key,value in [('request_id','e'*32),('candidate_id','f'*32),('plan_raw_hash','0'*64),('mode','TEST_FIXTURE'),('transport_channel','DUMP_RESTRICTED_LAB_EVALUATOR'),('flow_hash','0'*64),('process_session','')]:
            bad=copy.deepcopy(r);bad[key]=value
            with self.assertRaises(ValueError):checked_receipt(bad,self.plan,self.id,'b'*32)
    def test_receipt_missing_final_or_partial_rejected(self):
        for key,value in [('final_observation_complete',False),('verification_result',False),('completed_steps',0),('service_entry_hit',False),('final_status','UNCONFIRMED')]:
            r=self.receipt();r[key]=value
            with self.assertRaises(ValueError):checked_receipt(r,self.plan,self.id,'b'*32)
    def test_checked_receipt_accepts_only_current_setting_trial(self):
        self.assertTrue(checked_receipt(self.receipt(),self.plan,self.id,'b'*32))
    def test_preserved_state_change_rejected_even_if_success(self):
        r=self.receipt();r['initial_state']['bedroom_light.power']='off';r['final_observed_state']['bedroom_light.power']='on'
        with self.assertRaisesRegex(ValueError,'FORBIDDEN_SIDE_EFFECT'):checked_receipt(r,self.plan,self.id,'b'*32)
    def test_cancel_attempt_durable_and_late_receipt_cannot_publish(self):
        a=self.service.prepare(self.id,self.task['inputs']);self.service.cancel(self.id,a['attempt_id'])
        restarted=CandidateService(self.root/'lifecycle',self.inbox,'host.test',self.package,receipt_reader=lambda _:self.receipt())
        with self.assertRaisesRegex(ValueError,'CANCELLED_OR_STALE'):restarted.finish(self.id,a['attempt_id'])
    def test_only_one_pending_attempt(self):
        self.service.prepare(self.id,self.task['inputs'])
        with self.assertRaisesRegex(ValueError,'VALIDATION_PENDING'):self.service.prepare(self.id,self.task['inputs'])
    def test_restart_does_not_resume_or_issue_input(self):
        a=self.service.prepare(self.id,self.task['inputs'])
        s=CandidateService(self.root/'lifecycle',self.inbox,'host.test',self.package)
        self.assertFalse(s.inspect(self.id)['execution_authority'])
        self.assertEqual(s.inspect(self.id)['pending_attempt'],a['attempt_id'])
    def finish_prepared(self,*,no_action=False):
        a=self.service.prepare(self.id,self.task['inputs']);self.plan=a['plan']
        r=self.receipt();r['request_id']=a['attempt_id']
        if no_action:
            r['final_status']='NO_ACTION_REQUIRED';r['completion_boundary']['final_status']='NO_ACTION_REQUIRED'
            r['initial_state']=copy.deepcopy(r['final_observed_state'])
            for step in r['steps']:step['runtime_receipt']['execution_actions']=[]
            r['execution_actions']=[]
            for observation in r['observations']:observation['values']=copy.deepcopy(r['final_observed_state'])
        self.service.reader=lambda _:r
        return a,self.service.finish(self.id,a['attempt_id'])
    def test_actual_lifecycle_fixture_publish_and_reopen(self):
        a,row=self.finish_prepared();self.assertEqual(row['state'],'VALIDATED_SCOPE')
        self.assertFalse(row['formal_retrievable']);self.inbox.name(self.id,'same visible name')
        self.assertTrue(self.service.publish(self.id,confirmed=True)['formal_retrievable'])
        s=CandidateService(self.root/'lifecycle',self.inbox,'host.test',self.package)
        self.assertTrue(s.inspect(self.id)['formal_retrievable'])
        self.assertFalse(s.published(self.id)['execution_authority'])
        with self.assertRaises(ValueError):s.publish(self.id,confirmed=True)
    def test_already_satisfied_not_setting_capability(self):
        self.finish_prepared(no_action=True);self.inbox.name(self.id,'read only')
        with self.assertRaisesRegex(ValueError,'SETTING_CAPABILITY_NOT_TRIALED'):self.service.publish(self.id,confirmed=True)
    def test_finish_duplicate_cannot_add_second_proof(self):
        a,row=self.finish_prepared()
        with self.assertRaisesRegex(ValueError,'CANCELLED_OR_STALE'):self.service.finish(self.id,a['attempt_id'])
        self.assertEqual(len(self.service.inspect(self.id)['actual_points']),1)
    def test_receipt_goal_mismatch_stops_lifecycle(self):
        a=self.service.prepare(self.id,self.task['inputs']);self.plan=a['plan']
        r=self.receipt();r['request_id']=a['attempt_id'];r['final_observed_state']['bedroom_light.brightnessPercent']=59
        self.service.reader=lambda _:r
        with self.assertRaisesRegex(ValueError,'GOAL_NOT_VERIFIED|FINAL_OBSERVATION_MISSING'):self.service.finish(self.id,a['attempt_id'])
        self.assertEqual(self.service.inspect(self.id)['state'],'CHECKED')
        self.assertTrue((self.root/'lifecycle'/('receipt-'+a['attempt_id']+'.json')).exists())
    def test_expired_attempt_no_receipt_read(self):
        from unittest.mock import patch
        a=self.service.prepare(self.id,self.task['inputs']);calls=[];self.service.reader=lambda _:calls.append(1)
        with patch('c2_validation.time.time',return_value=a['expires_unix']+1):
            with self.assertRaisesRegex(ValueError,'VALIDATION_EXPIRED'):self.service.finish(self.id,a['attempt_id'])
        self.assertEqual(calls,[])
    def test_expired_preview_does_not_permanently_block_new_preview(self):
        from unittest.mock import patch
        a=self.service.prepare(self.id,self.task['inputs'])
        with patch('c2_validation.time.time',return_value=a['expires_unix']+1):
            b=self.service.prepare(self.id,self.task['inputs'])
        self.assertNotEqual(a['attempt_id'],b['attempt_id'])
        with self.service.db() as db:
            self.assertEqual(self.service._attempt(db,self.id,a['attempt_id'])[0],'EXPIRED')
    def test_clock_reversal_rejects_without_reading_receipt(self):
        from unittest.mock import patch
        a=self.service.prepare(self.id,self.task['inputs']);calls=[];self.service.reader=lambda _:calls.append(1)
        with patch('c2_validation.time.time',return_value=a['created_unix']-1):
            with self.assertRaisesRegex(ValueError,'VALIDATION_EXPIRED'):self.service.finish(self.id,a['attempt_id'])
        self.assertEqual(calls,[])
    def test_native_serialization_hash_not_canonical_hash(self):
        import hashlib
        r=self.receipt();r['native_plan_raw']=json.dumps(self.plan,ensure_ascii=False,sort_keys=False,separators=(',',':'))
        r['flow_plan_hash']=hashlib.sha256(r['native_plan_raw'].encode()).hexdigest()
        self.assertTrue(checked_receipt(r,self.plan,self.id,'b'*32))
        r['native_plan_raw']=canonical(dict(self.plan,task_id='task.foreign'))
        with self.assertRaises(ValueError):checked_receipt(r,self.plan,self.id,'b'*32)
    def test_sequence_and_action_evidence_missing_rejected(self):
        for mutate in (lambda r:r['observations'].pop(0),lambda r:r['observations'].reverse(),
            lambda r:r['steps'][0]['runtime_receipt']['execution_actions'][0].update(property='ac.temperatureC'),
            lambda r:r['steps'][0]['runtime_receipt']['execution_actions'][0].update(effect_verified=False),
            lambda r:r['event_scope_after'].update(original_filter_restored=False)):
            r=self.receipt();mutate(r)
            with self.assertRaises(ValueError):checked_receipt(r,self.plan,self.id,'b'*32)
    def test_c2_source_rebuilt_from_formal_store_not_self_report(self):
        from c2_lifecycle_cli import verify_current_published
        self.finish_prepared();self.inbox.name(self.id,'source')
        self.service.publish(self.id,confirmed=True);knowledge=self.service.published(self.id)
        # root is the deployment root; the fixture's lifecycle is its child.
        self.assertEqual(verify_current_published(self.root,knowledge),knowledge)
        for field,value in [('source_publication','f'*64),('parameter_slots',[]),('execution_authority',True)]:
            bad=copy.deepcopy(knowledge);bad[field]=value
            with self.assertRaises(ValueError):verify_current_published(self.root,bad)

if __name__=='__main__':unittest.main(verbosity=2)
