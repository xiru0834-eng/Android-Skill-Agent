from dataclasses import replace
import json
import sqlite3
from contextlib import closing
from test_adapter import AdapterTests
from p14deps import canonical, compiler, checks, environment, fixture_bundle
from records import PublishAuthority, RunEvidence
from flow_store import StoreError


class HardeningTests(AdapterTests):
    # Run independently registered edge cases; inherited tests are not counted twice.
    def test_H01_missing_candidate_authority_does_not_execute_published_version(self):
        self.publish()
        self.port.calls.clear()
        result = self.adapter.validate_candidate(self.store, self.key, self.task, None, lambda: self.policy, self.port)
        self.assertEqual(result.receipt['failure']['code'], 'VALIDATION_AUTHORITY_REQUIRED')
        self.assertEqual(self.port.calls, [])

    def test_H02_malformed_observation_fails_without_crashing_receipt(self):
        self.checked()
        original = self.port.observe
        self.port.observe = lambda plan, phase: replace(original(plan, phase), values_json='{bad')
        result = self.validate()
        self.assertEqual(result.receipt['failure']['code'], 'PRECONDITION_UNKNOWN')
        self.assertIsNone(result.evidence)

    def test_H03_scope_contains_only_known_semantic_properties(self):
        self.checked()
        self.port.state['authorization_ref'] = 'fake_exported_permission'
        result = self.validate()
        self.assertEqual(result.receipt['status'], 'SIMULATION_VERIFIED')
        scope = result.evidence.to_dict()
        self.assertNotIn('authorization_ref', scope['initial_state'])
        self.assertNotIn('authorization_ref', scope['final_state'])

    def test_H04_expired_and_wrong_session_before_dispatch(self):
        for change in ({'observation_session_id': 'old.session'}, {'captured_ms': -1}, {'sequence': 0}):
            with self.subTest(change=change):
                if not hasattr(self, 'key'):
                    self.checked()
                original = self.port.observe
                self.port.observe = lambda plan, phase, fn=original: replace(fn(plan, phase), **change)
                result = self.validate()
                self.assertEqual(result.receipt['failure']['code'], 'OBSERVATION_UNAVAILABLE')
                self.assertEqual(self.port.calls, [])
                self.port.observe = original

    def test_H05_environment_change_in_policy_blocks_all_input(self):
        self.checked()
        self.policy = replace(self.policy, environment_hash='changed')
        result = self.validate()
        self.assertEqual(result.receipt['failure']['code'], 'POLICY_BINDING_MISMATCH')
        self.assertEqual(self.port.calls, [])

    def test_H06_budget_not_renewed_after_first_call(self):
        self.flow['steps'].insert(0, dict(self.flow['steps'][0], id='first', argument={'kind': 'literal', 'value': 50}))
        self.checked()
        def observe(port, phase):
            if phase == 'set_value':
                self.policy = replace(self.policy, started_ms=100, deadline_ms=8100)
        self.port.on_observe = observe
        result = self.validate()
        self.assertEqual(result.receipt['failure']['code'], 'BUDGET_CONTEXT_CHANGED')
        self.assertEqual(len(self.port.calls), 1)

    def test_H07_real_device_publication_unavailable_not_faked(self):
        self.checked()
        result = self.validate()
        self.store.record_validation(self.key, 2, result.evidence)
        with self.assertRaises(StoreError) as caught:
            self.store.publish(self.key, 3, PublishAuthority(self.key, 'operator.test', self.policy.environment_hash, 'ANDROID_NATIVE', True))
        self.assertEqual(caught.exception.code, 'REAL_DEVICE_VALIDATION_REQUIRED')

    def test_H08_erroring_port_stops_no_retry(self):
        self.checked()
        self.port.on_call = lambda *_: (_ for _ in ()).throw(RuntimeError('untrusted error text'))
        result = self.validate()
        self.assertEqual(result.receipt['failure']['code'], 'EXECUTION_PORT_ERROR')
        self.assertEqual(len(self.port.calls), 1)
        self.assertIsNone(result.evidence)

    def test_H09_manual_state_change_not_old_trajectory(self):
        self.checked()
        self.port.on_observe = lambda port, phase: port.state.update({'bedroom_ac.power': 'on'}) if phase == 'set_value' else None
        result = self.validate()
        self.assertEqual(result.receipt['failure']['code'], 'STATE_CHANGED')
        self.assertEqual(self.port.calls, [])

    def test_H10_bad_import_digest_no_rights_or_partial_insert(self):
        self.checked()
        envelope = self.store.export_knowledge(self.key)
        envelope['sha256'] = '0' * 64
        with self.assertRaises(StoreError) as caught:
            self.store.import_knowledge(envelope, 1)
        self.assertEqual(caught.exception.code, 'IMPORT_DIGEST_ERROR')
        self.assertEqual(len(self.store.list_versions()), 1)

    def test_H11_stale_approval_cannot_dispatch(self):
        self.publish()
        self.port.calls.clear()
        self.policy = replace(self.policy, approved_raw_package_hash='stale', local_approval_verified=False)
        result = self.adapter.execute_published(self.store, self.key, self.task, lambda: self.policy, self.port)
        self.assertEqual(result.receipt['failure']['code'], 'LOCAL_REVIEW_REQUIRED')
        self.assertEqual(self.port.calls, [])

    def test_H12_known_unimplemented_read_adapter_not_silently_cleared(self):
        self.flow['unknowns'] = [{'id': 'unknown.read_adapter', 'description': 'not connected native port', 'impact': 'BLOCKS_EXECUTION'}]
        self.checked()
        result = self.validate()
        self.assertEqual(result.receipt['failure']['code'], 'BLOCKING_UNKNOWN')
        self.assertEqual(self.port.observations, [])

    def test_H13_reload_dto_mutation_cannot_publish_or_restore_authority(self):
        self.checked()
        row = self.store.load(self.key)
        row['state'], row['execution_authority'] = 'PUBLISHED', True
        result = self.adapter.execute_published(self.store, self.key, self.task, lambda: self.policy, self.port)
        self.assertEqual(result.receipt['failure']['code'], 'NOT_PUBLISHED')
        self.assertEqual(self.store.load(self.key)['state'], 'CHECKED')
        self.assertEqual(self.port.calls, [])

    def test_H14_native_style_policy_not_counted_as_simulation_evidence(self):
        self.checked()
        self.policy = replace(self.policy, source='TRUSTED_HOST_ADAPTER')
        result = self.validate()
        self.assertEqual(result.receipt['failure']['code'], 'EVIDENCE_CHANNEL_MISMATCH')
        self.assertEqual(self.port.calls, [])

    def test_H15_credentials_rejected_in_flow_and_package(self):
        for channel in ('flow', 'package'):
            with self.subTest(channel=channel):
                self.flow, self.package, self.task = fixture_bundle()
                fake_key = 'sk-proj-TESTONLY123456789'
                if channel == 'flow':
                    self.flow['purpose'] = fake_key
                else:
                    self.package['evidence'][0]['description'] = fake_key
                with self.assertRaises(StoreError) as caught:
                    self.store.save_draft(canonical(self.flow), self.package, 0)
                self.assertEqual(caught.exception.code, 'CREDENTIAL_CONTENT_REJECTED')
        self.assertEqual(self.store.list_versions(), [])


def load_tests(loader, tests, pattern):
    suite = loader.suiteClass()
    for name in sorted(name for name in dir(HardeningTests) if name.startswith('test_H')):
        suite.addTest(HardeningTests(name))
    return suite
