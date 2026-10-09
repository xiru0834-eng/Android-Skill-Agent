"""P3.2 protocol candidates only. This is not real learning or real device evidence."""
import copy
import json
from pathlib import Path
import unittest
from p33deps import p32, canonical, compiler, environment, trusted, P32
from layered_validation import format_layer, review_original, real_execution_gate


def fixtures():
    helper = trusted('test_abstraction', P32)
    req, raw, bundles = helper.fixtures(with_notes=True)
    pkg = json.loads(Path('D:/Codex-deliveries/smarthome-ui-polish/p1-2-flow-contracts/examples/valid-package.json').read_text(encoding='utf-8'))
    pkg['evidence'].append({'id': 'fixture.notes', 'kind': 'ILLUSTRATIVE',
                            'ref': 'example:synthetic-protocol-not-device',
                            'description': 'Synthetic contract fixture only; not current UI proof.'})
    task = json.loads(Path('D:/Codex-deliveries/smarthome-ui-polish/p1-2-flow-contracts/examples/valid-task.json').read_text(encoding='utf-8'))
    task['inputs']['percent'] = 80
    return req, raw, bundles, pkg, task


class LayerTests(unittest.TestCase):
    def test_missing_real_candidate_never_fills_default_or_compiles(self):
        req, _, bundles, pkg, task = fixtures()
        out = review_original(req, None, bundles, pkg, task)
        self.assertEqual(out['status'], 'BLOCKED_NO_CANDIDATE')
        self.assertEqual(out['layers']['format']['status'], 'NOT_TESTED')
        self.assertEqual(out['layers']['authorization']['status'], 'NOT_TESTED')
        self.assertIsNone(out['compiled_plan'])

    def test_format_and_compile_do_not_mean_business_or_authority_pass(self):
        req, raw, bundles, pkg, task = fixtures()
        before = copy.deepcopy((req, raw, bundles, pkg, task))
        out = review_original(req, raw, bundles, pkg, task)
        self.assertEqual(out['layers']['format']['status'], 'PASS')
        self.assertEqual(out['layers']['content']['status'], 'PENDING_CONFIRMATION')
        self.assertEqual(out['layers']['authorization']['status'], 'BLOCKED')
        self.assertFalse(out['execution_authority'])
        self.assertFalse(out['ready_for_device_execution'])
        self.assertEqual((req, raw, bundles, pkg, task), before)
        self.assertTrue(out['pending_items'])

    def test_later_illegal_argument_rejects_whole_plan_before_runtime(self):
        req, raw, bundles, pkg, task = fixtures()
        f = json.loads(raw)['candidate_flow']
        f['steps'].append({'id': 'bad_later', 'op': 'call', 'entity_input': 'light', 'capability': 'SetTemperature',
                           'argument': {'kind': 'literal', 'value': 999}})
        receipt, plan = format_layer(f, pkg, dict(task, inputs={'light': {'entity_id': 'bedroom_light'}}))
        self.assertEqual(receipt['status'], 'FAIL')
        self.assertIsNone(plan)

    def test_format_boundary_parameters_and_wrong_types(self):
        req, raw, bundles, pkg, task = fixtures()
        for bad in (-1, 101, True, 'very bright', None):
            with self.subTest(value=bad):
                changed = copy.deepcopy(task); changed['inputs']['percent'] = bad
                out = review_original(req, raw, bundles, pkg, changed)
                self.assertEqual(out['layers']['format']['status'], 'FAIL')
                self.assertIsNone(out['compiled_plan'])

    def test_evidence_presence_not_evidence_of_current_located_control(self):
        req, raw, bundles, pkg, task = fixtures()
        out = review_original(req, raw, bundles, pkg, task)
        self.assertIn('BINDING_NOT_INDEPENDENTLY_VERIFIED', {r['code'] for r in out['pending_items']})
        self.assertIn('ANDROID_FLOW_BRIDGE_NOT_CONNECTED', {r['code'] for r in out['pending_items']})
        self.assertTrue(all(r['current_ui_verified'] is False for r in out['layers']['content']['targets']))

    def test_no_model_consensus_or_boolean_can_supply_authority(self):
        receipt = real_execution_gate(None, {'confirmed': True, 'model_consensus': True}, None)
        self.assertEqual(receipt['status'], 'BLOCKED')
        self.assertEqual(receipt['code'], 'VALIDATION_AUTHORITY_REQUIRED')

    def test_known_native_transport_gap_cannot_be_claimed_connected(self):
        from p33deps import records
        class PretendNative:
            channel = 'ANDROID_NATIVE'
            connected = True
            def observe(self, *_): raise AssertionError('must not touch UI')
        receipt = real_execution_gate(None, records.ValidationAuthority('test.version', 'test.operator', True), PretendNative())
        self.assertEqual(receipt['code'], 'ANDROID_FLOW_BRIDGE_NOT_CONNECTED')
        self.assertFalse(receipt['device_execution_verified'])

    def test_source_mismatch_and_model_hypothesis_are_not_content_pass(self):
        req, raw, bundles, pkg, task = fixtures()
        bundles[0]['scope_summary']['limitations'].append('changed')
        out = review_original(req, raw, bundles, pkg, task)
        self.assertEqual(out['status'], 'MATERIAL_MISMATCH')
        self.assertIsNone(out['compiled_plan'])

    def test_wrong_host_entity_reference_and_environment_rejected(self):
        req, raw, bundles, pkg, task = fixtures()
        for field in ('host', 'environment', 'reference'):
            with self.subTest(field=field):
                p, t = copy.deepcopy(pkg), copy.deepcopy(task)
                if field == 'host': t['host_device_id'] = 'bedroom_light'
                elif field == 'environment': p['environment']['app_version'] = 'changed'
                else: t['flow_ref']['version'] = '99.0.0'
                out = review_original(req, raw, bundles, p, t)
                self.assertEqual(out['layers']['format']['status'], 'FAIL')

    def test_protection_and_unknown_steps_are_not_excluded_to_approve_candidate(self):
        req, raw, bundles, pkg, task = fixtures()
        out = review_original(req, raw, bundles, pkg, task)
        self.assertEqual([s['id'] for s in out['compiled_plan']['steps']],
                         ['read_power', 'check_power', 'set_brightness', 'check_brightness'])
        self.assertEqual([s['role'] for s in out['layers']['content']['steps']],
                         ['PROTECTION', 'PROTECTION', 'REQUIRED_BUSINESS', 'VERIFICATION'])
        self.assertIn('unknown.read_adapter', {r['code'] for r in out['pending_items']})

    def test_entity_evidence_mismatch_is_specific_pending_reason(self):
        req, raw, bundles, pkg, task = fixtures()
        # Both entities support power. The public notes still identify bedroom_light.
        # Keep original brightness task here: a supported but differently documented entity
        # must not be treated as proven merely because the capability catalog has it.
        profile = environment.audited_room_profile().to_dict()
        profile['targets']['bedroom_ac.brightnessPercent'] = dict(profile['targets']['bedroom_light.brightnessPercent'], entity_id='bedroom_ac')
        pkg['entities'][1]['capabilities'].append('SetBrightness')
        task['inputs']['light'] = {'entity_id': 'bedroom_ac'}
        out = review_original(req, raw, bundles, pkg, task, environment.EnvironmentProfile.test_fixture(profile))
        self.assertEqual(out['layers']['format']['status'], 'PASS')
        self.assertIn('ENTITY_EVIDENCE_MISMATCH', {r['code'] for r in out['pending_items']})

    def test_malformed_existing_authority_does_not_count_as_authorization(self):
        from p33deps import records
        out = real_execution_gate(None, records.ValidationAuthority('', '', True), None)
        self.assertEqual(out['code'], 'VALIDATION_AUTHORITY_REQUIRED')


if __name__ == '__main__': unittest.main()
