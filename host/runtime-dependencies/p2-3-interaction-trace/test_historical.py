"""Historical Android recordings are limited evidence, never current actions."""
import copy
import unittest
from historical_trace import import_catalog_material, adapt_legacy
from trace_contract import TraceError

class HistoricalTests(unittest.TestCase):
    def test_real_historical_file_retains_four_steps_and_actor_uncertainty(self):
        b=import_catalog_material('src.v46.pages')
        self.assertEqual(len(b['interactions']),4)
        self.assertEqual(b['source_raw'],'AUTOMATED')
        self.assertEqual(b['source_counts']['UNKNOWN'],4)
        self.assertEqual(b['source_counts']['AGENT_NAVIGATION'],0)
        self.assertEqual(b['real_verified_edges'],0)
        self.assertEqual(len(b['observed_transitions']),2)
        self.assertTrue(all(e['status']=='OBSERVED_HISTORICAL_LIMITED' for e in b['observed_transitions']))
        self.assertEqual(b['final']['saved'],[1,60,0,3])

    def test_missing_tree_dispatch_and_business_journal_stay_unknown(self):
        b=import_catalog_material('src.v46.pages')
        for step in b['interactions']:
            self.assertIsNone(step['before_observation_id'])
            self.assertIsNone(step['dispatch_id'])
            self.assertEqual(step['business_audit_status'],'UNAVAILABLE')
            self.assertFalse(step['execution_authority'])
        self.assertEqual(b['event_clock_domain'],'LEGACY_ACCESSIBILITY_EVENT_TIME_NOT_ELAPSED_PAIR')

    def test_no_input_paths_or_unknown_catalog_sources_followed(self):
        for value in ('../other.json','C:/Users/zz/secrets.txt','src.unknown',None):
            with self.assertRaises(TraceError):import_catalog_material(value)

    def test_legacy_human_claim_not_portable_approval(self):
        b=import_catalog_material('src.v46.pages');raw=b['original_trace']
        raw=copy.deepcopy(raw);raw['source']='HUMAN_DECLARED'
        adapted=adapt_legacy(raw,source_id='fixture.legacy',sha256='a'*64,evidence_ref='fixture:legacy')
        self.assertEqual(adapted['source_counts']['HUMAN_DEMONSTRATION'],4)
        self.assertFalse(adapted['execution_authority'])
        self.assertIn('HUMAN_CLAIM_NOT_AUTHENTICATED',adapted['limitations'])

    def test_legacy_bad_types_order_and_extra_secrets_are_rejected(self):
        raw=import_catalog_material('src.v46.pages')['original_trace']
        edits=(lambda r:r['steps'][0].update(eventTime=-1),
               lambda r:r['steps'][1].update(eventTime=1),
               lambda r:r['steps'][0].update(extra='secret'),
               lambda r:r['steps'][0]['before'].update(saved=object()),
               lambda r:r.update(source='AGENT_NAVIGATION'),
               lambda r:r.update(api_key='not.allowed'))
        for edit in edits:
            x=copy.deepcopy(raw);edit(x)
            with self.assertRaises(TraceError):
                adapt_legacy(x,source_id='fixture.legacy',sha256='a'*64,evidence_ref='fixture:legacy')

    def test_historical_labels_are_not_runtime_clues_or_navigation_permissions(self):
        b=import_catalog_material('src.v46.pages')
        self.assertEqual(b['runtime_permission'],None)
        self.assertEqual(b['learning_mode'],'HISTORICAL_LIMITED_NOT_AUTOMATIC_LEARNING')
        self.assertIsNone(b['host_device_id'])
        self.assertIsNone(b['current_ui_revision'])
