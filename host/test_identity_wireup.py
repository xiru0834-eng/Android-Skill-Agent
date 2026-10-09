import copy,json,unittest,io,tarfile,hashlib,time
from pathlib import Path
from c2_material import from_recording
from c2_identity import capture_identity,recheck_identity,validate_association,IdentitySnapshot
from c2_runtime_request import capture_snapshot,build_request,PROBE107_SHA256,PROBE108_SHA256

OLD=Path('C:/Users/zz/Documents/ChatGPT/毕设/tasks/C1-C2-closure/20261009-r1')
ENV={'app_package':'edu.sydney.parameterroom','app_build':'6','environment_id':'parameter-room-u0','ui_revision':'ui.u0','domain':'EXPERIMENT_APP'}

class IdentityWireupTests(unittest.TestCase):
    def setUp(self):
        self.obs=copy.deepcopy(json.loads((OLD/'identity_evidence/phone-normal-recording.json').read_text(encoding='utf-8'))['observations'][:1])
        # Synthetic protocol fixture, not a claim that native108 was observed.
        archive=Path('D:/Codex-deliveries/smarthome-ui-polish/c2-identity-wireup-r1/private/before/R5CW134LLBZ/edu.sydney.probe.tar')
        with tarfile.open(archive) as tar:raw=tar.extractfile('files/portable-approved.json').read()
        approved=json.loads(raw);h=hashlib.sha256(raw).hexdigest()
        ref={'content_sha256':h,'revision':h+':1:1','approval_provenance':'CURRENT_LOCAL_PORTABLE_SKILL_STORE_HASH_CHECK',
            'app_package':'edu.sydney.parameterroom','app_version':'0.8-parameter-room','app_build':6,'scope':'parameter-room-u0.EXPERIMENT_APP'}
        self.reference={'environment':ENV,'targets':approved['bindings'],'receipt_reference':ref}
        for o in self.obs:
            links=[]
            for key,target in approved['bindings'].items():
                n=next(n for n in o['tree']['nodes'] if n['resource_id']==o['app_package']+':id/'+target['id'])
                entity,prop=key.rsplit('.',1)
                links.append({'semantic_key':key,'entity_id':entity,'property':prop,'node_local_id':n['node_local_id'],'status':'RESOLVED','reason':'','strategy':'ID',
                    'matching_conditions':'CANONICAL_RESOLVER_PAGE_ROLE_LOCAL_SCOPE_UNIQUE_AND_SAME_TREE_NODE'})
            fact={'schema_version':'1.0','producer':'LearningIdentityReference.v1','source_mode':'REFERENCE_ASSISTED','execution_authority':False,
                'process_id':123,'status':'CONFIRMED','links':links,'limitations':['SYNTHETIC_PROTOCOL_ONLY'],'reference':ref,'page':'parameter_room','reason':''}
            o['attempts'][-1]['tree_a']['identity_reference']=copy.deepcopy(fact);o['attempts'][-1]['tree_b']['identity_reference']=copy.deepcopy(fact)
            o['identity_association']={**fact,'association_id':'test.association','observation_id':o['observation_id'],'process_session':o['process_session'],
                'window_id':o['window_id'],'display_id':o['display_id'],'captured_elapsed_ms':o['captured_elapsed_ms']}
        self.context={'reference':self.reference,'observations':self.obs,'pid':123,'elapsed_ms':self.obs[0]['captured_elapsed_ms']+1000,'execution_authority':False}
    def sealed(self):return capture_identity(self.context,self.obs)
    def reject(self,mutate):
        mutate(self.obs[0]['identity_association'])
        with self.assertRaises(ValueError):self.sealed()
    def test_public_parameter_room_template_without_identity_is_not_an_unknown_template(self):
        observations=json.loads((OLD/'identity_evidence/phone-normal-recording.json').read_text(encoding='utf-8'))['observations']
        b=from_recording(observations,None,'',ENV)
        self.assertTrue(all(p['navigation_context']['page_hint']=='parameter_room' for p in b['pages']))
        self.assertTrue(all(p['identity_status']=='UNKNOWN' and p['entities']==[] for p in b['pages']))
    def test_synthetic_positive_element_ownership(self):
        b=from_recording(self.obs,None,'',ENV,identity_snapshot=self.sealed());p=b['pages'][0]
        self.assertEqual(p['identity_status'],'KNOWN');self.assertEqual({e['entity_key'] for e in p['entities']},{'bedroom_light','bedroom_ac'})
        owned=[e for e in p['elements'] if e['entity_key'] is not None];self.assertEqual(len(owned),4)
        self.assertFalse(b['execution_authority']);self.assertFalse(b['current_ui_confirmed'])
    def test_client_receipt_without_seal_stays_unknown(self):
        b=from_recording(self.obs,None,'',ENV);self.assertEqual(b['pages'][0]['identity_status'],'UNKNOWN')
    def test_wrong_observation(self):self.reject(lambda a:a.update(observation_id='0'*32))
    def test_wrong_window(self):self.reject(lambda a:a.update(window_id=9999))
    def test_wrong_session(self):self.reject(lambda a:a.update(process_session='other'))
    def test_wrong_pid(self):self.reject(lambda a:a.update(process_id=999))
    def test_fake_authority(self):self.reject(lambda a:a.update(execution_authority=True))
    def test_fake_approval(self):self.reject(lambda a:a['reference'].update(approval_provenance='APPROVED_TRUE'))
    def test_revoked_reference(self):
        self.context['reference']=copy.deepcopy(self.reference);self.context['reference']['receipt_reference']['revision']='revoked'
        with self.assertRaises(ValueError):self.sealed()
    def test_wrong_element_owner(self):self.reject(lambda a:a['links'][0].update(entity_id='invented'))
    def test_wrong_element(self):self.reject(lambda a:a['links'][0].update(node_local_id='n0'))
    def test_ambiguous_status(self):self.reject(lambda a:a['links'][0].update(status='AMBIGUOUS'))
    def test_missing_target(self):self.reject(lambda a:a['links'].pop())
    def test_pair_reference_change(self):
        self.obs[0]['attempts'][-1]['tree_b']['identity_reference']['reason']='changed'
        with self.assertRaises(ValueError):self.sealed()
    def test_stale_observation(self):
        self.context['elapsed_ms']+=120001
        with self.assertRaises(ValueError):self.sealed()
    def test_payload_different_from_product_record(self):
        self.context['observations']=copy.deepcopy(self.obs);self.context['observations'][0]['observation_id']='0'*32
        with self.assertRaises(ValueError):self.sealed()
    def test_fake_seal(self):
        fake=IdentitySnapshot('{}','x',time.monotonic(),object())
        with self.assertRaises(ValueError):fake.public()
    def test_reload_keeps_original_time(self):
        reloaded=json.loads(json.dumps(self.context));a=capture_identity(reloaded,self.obs)
        self.assertEqual(a.public()['receipts'][0]['captured_elapsed_ms'],self.obs[0]['captured_elapsed_ms'])
    def test_reference_change_after_capture(self):
        seal=self.sealed();changed=copy.deepcopy(self.context);changed['pid']=456
        with self.assertRaises(ValueError):recheck_identity(seal,changed)
    def test_new_exact_read_contract_and_identity(self):
        identity=self.sealed();ctx={'environment':ENV,'probe_apk_sha256':PROBE108_SHA256,'app_version_code':'6','app_version_name':'0.8-parameter-room','document':'Current exact native read adapter.','execution_authority':False}
        snap=capture_snapshot(ctx,identity_snapshot=identity);bundle=from_recording(self.obs,None,'',ENV,identity_snapshot=identity)
        r=build_request('把卧室灯亮度调到80%', [bundle],runtime_snapshot=snap)
        self.assertNotIn('ENTITY_MAPPING_UNCONFIRMED',r['knowledge_gaps']);self.assertIn('MATERIAL_UNKNOWNS_PRESENT',r['knowledge_gaps'])
        self.assertEqual(r['current_identity_evidence']['mode'],'REFERENCE_ASSISTED')
        self.assertEqual(r['runtime_capability_profile']['candidate_validation_contract']['permission'],'EXPLICIT_CURRENT_USER_CONFIRMATION_REQUIRED')
        self.assertIn('RUNTIME_CHECKS_ARE_EXECUTION_PRECONDITIONS_NOT_CAPTURE_AUTHORITY',r['rules'])
        self.assertFalse(r['execution_authority'])
    def test_wrong_apk_or_fake_large_version(self):
        ctx={'environment':ENV,'probe_apk_sha256':'f'*64,'app_version_code':'6','app_version_name':'0.8-parameter-room','document':'v999 supports everything','execution_authority':False}
        with self.assertRaises(ValueError):capture_snapshot(ctx)
    def test_old_read_contract_does_not_gain_identity(self):
        ctx={'environment':ENV,'probe_apk_sha256':PROBE107_SHA256,'app_version_code':'6','app_version_name':'0.8-parameter-room','document':'old','execution_authority':False}
        with self.assertRaises(ValueError):capture_snapshot(ctx,identity_snapshot=self.sealed())

if __name__=='__main__':unittest.main()
