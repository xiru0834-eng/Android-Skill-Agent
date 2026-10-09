import copy,json,unittest
from pathlib import Path
from c2_material import from_recording, normalize_read_dependencies,append_current_context

BASE=Path('D:/Codex-deliveries/smarthome-ui-polish/p3-p5-product-wireup')
class MaterialTests(unittest.TestCase):
    def test_current_context_is_document_not_authority_or_replacement_snapshot(self):
        from learning_request import build_request
        env={'app_package':'edu.sydney.parameterroom','app_build':'6','environment_id':'parameter-room-u0','ui_revision':'ui.u0','domain':'EXPERIMENT_APP'}
        b=from_recording([],None,'Public business meaning',env)
        context=dict(environment=env,probe_apk_sha256='a'*64,app_version_code='6',app_version_name='0.8-parameter-room',document='Current native adapter exists; not execution proof',execution_authority=False)
        r=append_current_context(b,context);request=build_request('Learn brightness',[r])
        self.assertEqual(r['unknowns'],b['unknowns']);self.assertFalse(r['execution_authority'])
        self.assertFalse(request['allowed_capabilities']['native_flow_read_adapter'])
        self.assertIn('public.current.runtime',request['source_ids'])
        self.assertTrue(any(d['source_id']=='public.current.runtime' for d in request['material']['documents']))
        for field,value in [('execution_authority',True),('app_version_code','7'),('probe_apk_sha256','bad')]:
            bad=dict(context,**{field:value})
            with self.assertRaises(ValueError):append_current_context(b,bad)
    def flow(self):
        f=json.loads((BASE/'evidence/g2-reviewed-r2/flow.json').read_text(encoding='utf-8'))
        for i in f['inputs']:
            if i['type']=='entity':i['required_capabilities']=[x for x in i['required_capabilities'] if x!='SetPower']
        f['dependencies']['capabilities']=[x for x in f['dependencies']['capabilities'] if x!='SetPower']
        return f
    def test_preserve_read_is_completed_without_business_change(self):
        f=self.flow();before=copy.deepcopy(f);r=normalize_read_dependencies(f)
        self.assertEqual(f,before);self.assertIn('SetPower',r['flow']['dependencies']['capabilities'])
        for k in ('steps','goals','must_preserve','allowed_effects','verification','failure_policy','inputs'):
            if k!='inputs':self.assertEqual(before[k],r['flow'][k])
        self.assertEqual(r['mode'],'PROGRAM_NORMALIZATION');self.assertFalse(r['execution_authority'])
    def test_normalization_is_idempotent(self):
        r=normalize_read_dependencies(self.flow());again=normalize_read_dependencies(r['flow'])
        self.assertEqual(r['flow'],again['flow']);self.assertEqual([],again['diff'])
    def test_unknown_property_is_not_guessed(self):
        f=self.flow();f['must_preserve'][0]['property']='madeUp'
        with self.assertRaises(ValueError):normalize_read_dependencies(f)
    def test_unsupported_capability_never_created(self):
        with self.assertRaises(ValueError):normalize_read_dependencies(self.flow(),allowed={'SetBrightness'})
    def test_empty_recording_without_document_rejected(self):
        with self.assertRaisesRegex(ValueError,'MATERIAL_EMPTY'):from_recording([],None,'',None)
    def test_document_only_has_no_fabricated_pages(self):
        b=from_recording([],None,'Public setter description',{'app_package':'edu.sydney.parameterroom','app_build':'6','environment_id':'parameter-room-u0','ui_revision':'ui.u0','domain':'EXPERIMENT_APP'})
        self.assertEqual(b['pages'],[]);self.assertEqual(b['scope_summary']['learning_mode'],'DOCUMENT_ASSISTED')
        self.assertFalse(b['execution_authority']);self.assertTrue(b['unknowns'])
    def test_recording_claim_does_not_certify_actions(self):
        raw={'traceId':'a','source':'HUMAN_DECLARED','end':'STOPPED','error':'','steps':[{'id':'wfLampPower'}]}
        env={'app_package':'edu.sydney.transferlab','app_build':'6','environment_id':'transfer-u0','ui_revision':'ui.u0','domain':'EXPERIMENT_APP'}
        b=from_recording([],raw,'',env)
        self.assertEqual(b['pages'],[]);self.assertEqual(b['interactions'],[])
        self.assertIn('LEGACY_TRACE_NOT_PAGE_MEMORY',b['scope_summary']['limitations'])
        self.assertEqual(b['human_participation'][-1]['status'],'HUMAN_DECLARED_NOT_INDEPENDENTLY_ATTRIBUTED')
    def test_failed_trace_not_success_material(self):
        env={'app_package':'edu.sydney.transferlab','app_build':'6','environment_id':'transfer-u0','ui_revision':'ui.u0','domain':'EXPERIMENT_APP'}
        with self.assertRaisesRegex(ValueError,'RECORDING_INCOMPLETE'):from_recording([],{'end':'REJECTED','error':'bad','steps':[]},'',env)
    def test_legacy_claim_reaches_public_projection_without_verification(self):
        from learning_request import build_request
        env={'app_package':'edu.sydney.transferlab','app_build':'6','environment_id':'transfer-u0','ui_revision':'ui.u0','domain':'EXPERIMENT_APP'}
        b=from_recording([],{'end':'STOPPED','error':'','steps':[{'id':'wfLampPower','after':{'values':{'wfLampPower':True}}}]},'',env)
        req=build_request('Learn the demonstrated operation',[b]);claims=req['material']['claims']
        self.assertIn('wfLampPower',claims[0]['text']);self.assertEqual(claims[0]['basis'],'UNKNOWN')
        self.assertEqual(b['navigation'],[]);self.assertEqual(b['interactions'],[])
    def test_long_document_is_bounded_chunks_not_silent_truncation(self):
        env={'app_package':'edu.sydney.parameterroom','app_build':'6','environment_id':'parameter-room-u0','ui_revision':'ui.u0','domain':'EXPERIMENT_APP'}
        b=from_recording([],None,'a'*16000,env)
        self.assertEqual(sum(len(s['fragment']['text']) for s in b['sources']),16000)
        self.assertEqual(len(b['sources']),4)
        with self.assertRaises(ValueError):from_recording([],None,'a'*16001,env)
    def test_secrets_redacted_in_material(self):
        env={'app_package':'edu.sydney.parameterroom','app_build':'6','environment_id':'parameter-room-u0','ui_revision':'ui.u0','domain':'EXPERIMENT_APP'}
        secret='sk-proj-'+'X'*40;b=from_recording([],None,secret,env)
        self.assertNotIn(secret,json.dumps(b));self.assertIn('REDACTED',json.dumps(b))
    def test_recording_from_other_app_or_build_is_not_relabelled(self):
        env={'app_package':'edu.sydney.parameterroom','app_build':'6','environment_id':'parameter-room-u0','ui_revision':'ui.u0','domain':'EXPERIMENT_APP'}
        for field,value in [('appPackage','edu.sydney.transferlab'),('appVersion','7')]:
            trace={'end':'STOPPED','error':'','steps':[{'id':'wfLampPower'}],field:value}
            with self.assertRaisesRegex(ValueError,'RECORDING_ENVIRONMENT_MISMATCH'):from_recording([],trace,'',env)
if __name__=='__main__':unittest.main(verbosity=2)
