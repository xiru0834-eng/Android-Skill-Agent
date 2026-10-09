"""Isolated source/HTTP contract tests. No ADB, model or business action."""
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from c2_usage_bridge import C2FlowServer
from flow_bridge import model_body,typed_inputs

class ParameterEvidenceTests(unittest.TestCase):
    def setUp(self):
        import json
        path=Path('C:/Users/zz/Documents/ChatGPT/毕设/tasks/C2-identity-wireup/20261009-r1/normal-journey-r3/publication.json')
        self.catalog=json.loads(path.read_text(encoding='utf-8'))['current_published']['catalog']
    def test_prompt_distinguishes_legal_domain_from_observed_points(self):
        body=model_body('set brightness to 40 percent',self.catalog)
        prompt=body['input'][0]['content']
        self.assertIn('verified_parameters are test history, not an allowed-value list',prompt)
        self.assertIn('never claim the entire domain was tested',prompt)
        self.assertIn('Current local approval and per-task confirmation remain required',prompt)
    def test_request_keeps_exact_catalog_and_verification_limits(self):
        import json
        original=copy.deepcopy(self.catalog);body=model_body('set brightness to 40 percent',self.catalog)
        payload=json.loads(body['input'][1]['content'])
        self.assertEqual(payload['published_flows'],original)
        self.assertEqual(self.catalog,original)
        self.assertFalse(payload['published_flows'][0]['whole_parameter_domain_verified'])
    def test_unobserved_legal_values_do_not_expand_declared_domain(self):
        entry=self.catalog[0]
        for value in (40,90):
            rows=[{'name':'light','type':'entity','value':'bedroom_light'},{'name':'percent','type':'integer','value':str(value)}]
            self.assertEqual(typed_inputs(rows,entry)['percent'],value)
        for value in (-1,101):
            rows=[{'name':'light','type':'entity','value':'bedroom_light'},{'name':'percent','type':'integer','value':str(value)}]
            with self.assertRaisesRegex(ValueError,'INPUT_RANGE'):typed_inputs(rows,entry)

class SourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        with patch('c2_usage_bridge.LifecycleClient') as lifecycle:
            self.lifecycle=lifecycle.return_value
            self.server=C2FlowServer(('127.0.0.1',0),'a'*48,Path(self.tmp.name)/'learning',Path(self.tmp.name)/'audit','R5CW134LLBZ',max_calls=1)
        self.addCleanup(self.server.server_close)
    def test_empty_start_does_not_claim_formal_catalog(self):self.assertEqual(self.server.knowledge,{})
    def test_missing_formal_source_cannot_replace_current(self):
        self.lifecycle.current_published.side_effect=ValueError('FORMAL_FLOW_NOT_AVAILABLE')
        with self.assertRaises(ValueError):self.server.refresh_source()
        self.assertEqual(self.server.knowledge,{})
    def test_active_selection_pins_source_and_prevents_refresh(self):
        self.server.knowledge={'catalog':['original']};self.server.lock.acquire()
        try:
            with self.assertRaisesRegex(ValueError,'REMOTE_BUSY'):self.server.refresh_source()
            self.lifecycle.current_published.assert_not_called()
            self.assertEqual(self.server.knowledge,{'catalog':['original']})
        finally:self.server.lock.release()
    def test_source_is_copied_and_rechecked(self):
        current={'catalog':['verified']};self.lifecycle.current_published.return_value=current
        self.server.refresh_source();current['catalog'].append('changed')
        self.assertEqual(self.server.knowledge,{'catalog':['verified']})
        with self.assertRaisesRegex(ValueError,'CURRENT_FORMAL_SOURCE_CHANGED'):self.server.verify_source()
    def test_unchanged_source_passes_without_model_call(self):
        self.lifecycle.current_published.return_value={'catalog':['verified']}
        self.server.refresh_source();self.server.verify_source();self.assertEqual(self.server.count,0)

if __name__=='__main__':unittest.main()
