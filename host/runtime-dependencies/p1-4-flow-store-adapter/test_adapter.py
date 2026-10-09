from dataclasses import replace
import tempfile
from pathlib import Path
import unittest
from p14deps import fixture_bundle, compiler, environment, canonical, digest, checks
from flow_store import FlowStore, StoreError
from records import PublishAuthority, ValidationAuthority, RunEvidence
from flow_adapter import FlowAdapter, route_entry
from test_support import Clock, RoomPort, policy_for, STATE


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p14-adapter-')
        self.store = FlowStore.create(Path(self.temp.name))
        self.flow, self.package, self.task = fixture_bundle()
        self.clock = Clock()
        self.port = RoomPort(self.clock)
        self.adapter = FlowAdapter(enabled=True, clock=self.clock)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def checked(self):
        row = self.store.save_draft(canonical(self.flow), self.package, 0)
        self.key = row['key']
        self.store.check(self.key, 1, self.task, None)
        plan = compiler.compile_flow(self.flow, self.package, self.task, None)
        self.policy = policy_for(plan)
        self.authority = ValidationAuthority(self.key, 'operator.test_fixture', True)
        return plan

    def validate(self):
        return self.adapter.validate_candidate(self.store, self.key, self.task, self.authority,
                                                lambda: self.policy, self.port)

    def publish(self):
        self.checked()
        result = self.validate()
        self.assertEqual(result.receipt['status'], 'SIMULATION_VERIFIED')
        row = self.store.record_validation(self.key, 2, result.evidence)
        authority = PublishAuthority(self.key, 'operator.test_fixture', self.policy.environment_hash, 'LOGIC_SIMULATION', True)
        return self.store.publish(self.key, row['revision'], authority)

    def test_A01_compile_dispatch_reobserve_and_scope(self):
        self.checked()
        result = self.validate()
        self.assertEqual(result.receipt['status'], 'SIMULATION_VERIFIED')
        self.assertEqual(len(self.port.calls), 1)
        self.assertIn('AFTER.set_value', self.port.observations)
        row = self.store.record_validation(self.key, 2, result.evidence)
        scope = row['scopes'][0]
        self.assertEqual(scope['inputs']['value'], 80)
        self.assertEqual(scope['initial_state']['bedroom_light.brightnessPercent'], 20)
        self.assertEqual(scope['final_state']['bedroom_light.brightnessPercent'], 80)
        self.assertEqual(scope['channel'], 'LOGIC_SIMULATION')
        self.assertFalse(row['execution_authority'])
        self.assertFalse(row['device_execution_verified'])

    def test_A02_all_three_actual_skills(self):
        for skill, value, entity in [('SetPower', 'on', 'bedroom_light'), ('SetPower', 'on', 'bedroom_ac'),
                                    ('SetBrightness', 100, 'bedroom_light'), ('SetTemperature', 16, 'bedroom_ac')]:
            with self.subTest(skill=skill, entity=entity):
                self.flow, self.package, self.task = fixture_bundle(skill, value)
                self.task['inputs']['entity']['entity_id'] = entity
                self.flow['id'] = 'flow.test_' + skill.lower() + '_' + entity
                self.package['flow_refs'][0]['id'] = self.flow['id']
                self.task['flow_ref']['id'] = self.flow['id']
                self.checked()
                self.port = RoomPort(self.clock)
                result = self.validate()
                self.assertEqual(result.receipt['status'], 'SIMULATION_VERIFIED')
                self.assertEqual(self.port.calls[0]['call']['skill'], skill)

    def test_A03_explicit_ABA_not_collapsed(self):
        self.task['inputs']['value'] = 20
        self.flow['steps'] = [dict(id='s' + str(i), op='call', capability='SetBrightness', entity_input='entity',
                                  argument={'kind': 'literal', 'value': v}) for i, v in enumerate([80, 20])]
        self.checked()
        result = self.validate()
        self.assertEqual([r['call']['args']['percent'] for r in self.port.calls], [80, 20])
        self.assertEqual(result.receipt['completed_calls'], 2)
        self.assertEqual(result.receipt['status'], 'SIMULATION_VERIFIED')

    def test_A04_ordered_read_and_assert_with_fresh_state(self):
        target = self.flow['allowed_effects'][0]
        self.flow['steps'].insert(0, {'id': 'read_before', 'op': 'read', 'target': target})
        self.flow['steps'].insert(1, {'id': 'assert_before', 'op': 'assert',
            'predicate': {'op': 'equals', 'left': {'kind': 'read', 'step_id': 'read_before'},
                          'right': {'kind': 'literal', 'value': 20}}})
        self.checked()
        result = self.validate()
        self.assertEqual(result.receipt['completed_steps'], 3)
        self.assertEqual(self.port.observations, ['ENTRY', 'read_before', 'assert_before', 'set_value', 'AFTER.set_value', 'FINAL'])

    def test_A05_same_state_no_dispatch_is_not_set_capability_proof(self):
        self.port.state['bedroom_light.brightnessPercent'] = 80
        self.checked()
        result = self.validate()
        self.assertEqual(result.receipt['status'], 'SIMULATION_VERIFIED')
        self.assertEqual(result.receipt['dispatch_count'], 0)
        self.assertTrue(result.evidence.to_dict()['read_only_target_satisfied'])

    def test_A06_wrong_parameters_before_io(self):
        self.checked()
        self.task['inputs']['value'] = 101
        result = self.validate()
        self.assertEqual(result.receipt['status'], 'REJECTED')
        self.assertEqual(self.port.observations, [])
        self.assertEqual(self.port.calls, [])

    def test_A07_no_effect_not_false_success(self):
        self.checked()
        self.port.on_call = lambda *_: {'final_status': 'SUCCESS', 'verification_result': True}
        result = self.validate()
        self.assertIsNone(result.evidence)
        self.assertEqual(result.receipt['failure']['code'], 'VERIFICATION_ERROR')
        self.assertEqual(result.receipt['completed_calls'], 0)

    def test_A08_forbidden_side_effect_stops(self):
        self.checked()
        def side_effect(port, call):
            port.apply(call)
            port.state['bedroom_ac.power'] = 'on'
            return {'final_status': 'SUCCESS', 'verification_result': True}
        self.port.on_call = side_effect
        result = self.validate()
        self.assertEqual(result.receipt['failure']['code'], 'FORBIDDEN_SIDE_EFFECT')
        self.assertIsNone(result.evidence)

    def test_A09_ack_not_terminal_verification(self):
        self.checked()
        self.port.on_call = lambda *_: {'accepted': True}
        result = self.validate()
        self.assertEqual(result.receipt['failure']['code'], 'LEGACY_RESULT_UNCONFIRMED')

    def test_A10_cancel_before_input(self):
        self.checked()
        self.policy = replace(self.policy, cancelled=True)
        result = self.validate()
        self.assertEqual(result.receipt['failure']['code'], 'CANCELLED')
        self.assertEqual(self.port.observations, [])
        self.assertEqual(self.port.calls, [])

    def test_A11_same_deadline_through_multiple_calls(self):
        self.flow['steps'].insert(0, dict(self.flow['steps'][0], id='first', argument={'kind': 'literal', 'value': 50}))
        self.checked()
        result = self.validate()
        self.assertEqual(result.receipt['status'], 'SIMULATION_VERIFIED')
        self.assertEqual([r['deadline_ms'] for r in self.port.calls], [8000, 8000])

    def test_A12_timeout_no_new_business_input(self):
        self.checked()
        self.clock.now = 8000
        result = self.validate()
        self.assertEqual(result.receipt['failure']['code'], 'BUDGET_INSUFFICIENT')
        self.assertEqual(self.port.calls, [])

    def test_A13_source_cannot_self_report_real_android(self):
        self.checked()
        self.port.channel = 'ANDROID_NATIVE'
        result = self.validate()
        self.assertEqual(result.receipt['failure']['code'], 'NATIVE_TRANSPORT_NOT_CONNECTED')
        self.assertEqual(self.port.observations, [])

    def test_A14_cancel_between_materialize_and_dispatch(self):
        self.checked()
        def observe(port, phase):
            if phase == 'set_value':
                self.policy = replace(self.policy, cancelled=True)
        self.port.on_observe = observe
        result = self.validate()
        self.assertEqual(result.receipt['failure']['code'], 'CANCELLED')
        self.assertEqual(self.port.calls, [])

    def test_A15_partial_success_preserved_not_whole_success(self):
        self.flow['steps'].insert(0, dict(self.flow['steps'][0], id='first', argument={'kind': 'literal', 'value': 50}))
        self.checked()
        def call(port, action):
            if len(port.calls) == 1:
                port.apply(action)
            return {'final_status': 'SUCCESS', 'verification_result': True}
        self.port.on_call = call
        result = self.validate()
        self.assertEqual(result.receipt['completed_calls'], 1)
        self.assertEqual(result.receipt['status'], 'UNCONFIRMED')
        self.assertIsNone(result.evidence)

    def test_L03_publish_is_not_permission_and_new_task_requires_policy(self):
        row = self.publish()
        self.assertEqual(row['state'], 'PUBLISHED')
        self.port = RoomPort(self.clock)
        result = self.adapter.execute_published(self.store, self.key, self.task, lambda: None, self.port)
        self.assertEqual(result.receipt['failure']['code'], 'POLICY_CONTEXT_UNAVAILABLE')
        self.assertEqual(self.port.calls, [])

    def test_L04_candidate_not_executable_via_published_entry(self):
        self.checked()
        result = self.adapter.execute_published(self.store, self.key, self.task, lambda: self.policy, self.port)
        self.assertEqual(result.receipt['failure']['code'], 'NOT_PUBLISHED')
        self.assertEqual(self.port.observations, [])

    def test_L05_model_dictionary_not_validation_or_publish_authority(self):
        self.checked()
        with self.assertRaises(StoreError):
            self.store.record_validation(self.key, 2, {'sequence_verified': True})
        with self.assertRaises(StoreError):
            self.store.publish(self.key, 2, {'confirmed': True})
        result = self.adapter.validate_candidate(self.store, self.key, self.task, {'confirmed': True}, lambda: self.policy, self.port)
        self.assertEqual(result.receipt['failure']['code'], 'VALIDATION_AUTHORITY_REQUIRED')

    def test_L06_published_execution_still_recompiles_and_observes(self):
        self.publish()
        self.port = RoomPort(self.clock)
        result = self.adapter.execute_published(self.store, self.key, self.task, lambda: self.policy, self.port)
        self.assertEqual(result.receipt['status'], 'SIMULATION_VERIFIED')
        self.assertEqual(self.port.observations[0], 'ENTRY')
        self.assertEqual(len(self.port.calls), 1)

    def test_L07_revocation_during_task_prevents_next_input(self):
        self.publish()
        self.port = RoomPort(self.clock)
        self.port.on_observe = lambda port, phase: self.store.invalidate(self.key, 4, 'REVOKED', 'operator.cancel') if phase == 'set_value' else None
        result = self.adapter.execute_published(self.store, self.key, self.task, lambda: self.policy, self.port)
        self.assertEqual(result.receipt['failure']['code'], 'KNOWLEDGE_REVOKED')
        self.assertEqual(self.port.calls, [])

    def test_L08_export_import_starts_DRAFT_without_rights(self):
        self.publish()
        envelope = self.store.export_knowledge(self.key)
        with tempfile.TemporaryDirectory(prefix='p14-import-') as root:
            other = FlowStore.create(root)
            try:
                row = other.import_knowledge(envelope, 0)
                self.assertEqual(row['state'], 'DRAFT')
                self.assertEqual(row['scopes'], [])
                self.assertFalse(row['resume_authority'])
            finally:
                other.close()

    def test_A16_default_off_does_not_read_new_store_or_touch_port(self):
        off = FlowAdapter()
        result = off.execute_published(None, 'invalid', None, None, None)
        self.assertEqual(result.receipt['status'], 'FEATURE_DISABLED')
        invoked = []
        raw = object()
        legacy = lambda value: invoked.append(value) or 'old-receipt'
        new = lambda _: self.fail('new route must not be inspected')
        self.assertEqual(route_entry(False, legacy, new, raw), 'old-receipt')
        self.assertIs(invoked[0], raw)


if __name__ == '__main__':
    unittest.main()
