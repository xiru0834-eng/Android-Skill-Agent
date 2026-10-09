import copy
import json
import unittest
from test_abstraction import fixtures
from test_revision import edit_notes
from abstraction import analyze
from revision import propose_parameterization
from p32deps import bundle_contract, canonical, p31_request


def capability_fixture(kind, demonstration):
    req, raw, bundles = fixtures(with_notes=True)
    d = json.loads(raw); flow = d['candidate_flow']
    notes = bundles[0]['sources'][0]['fragment']['public_flow_notes']
    group = notes['parameter_groups'][0]
    if kind == 'SetTemperature':
        entity, prop, parameter = 'bedroom_ac', 'temperatureCelsius', 'celsius'
        group['domain'] = {'type': 'integer', 'minimum': 16, 'maximum': 30, 'step': 1, 'unit': 'celsius'}
    else:
        entity, prop, parameter = 'bedroom_light', 'power', 'state'
        group['domain'] = {'type': 'enum', 'choices': ['off', 'on'], 'unit': 'enum'}
    flow['inputs'][0]['required_capabilities'] = [kind] if kind == 'SetPower' else ['SetPower', kind]
    flow['steps'][2]['capability'] = kind
    flow['steps'][3]['predicate']['left']['property'] = prop
    flow['goals'][0]['left']['property'] = prop
    flow['allowed_effects'][0]['property'] = prop
    if kind == 'SetPower': flow['must_preserve'] = []
    flow['dependencies']['capabilities'] = flow['inputs'][0]['required_capabilities']
    for node in (flow['steps'][2]['argument'], flow['steps'][3]['predicate']['right'], flow['goals'][0]['right']):
        node['value'] = demonstration
    notes['entity_evidence'][0].update(entity_id=entity, supported_capabilities=flow['inputs'][0]['required_capabilities'])
    group.update(property=prop, name=parameter)
    s = bundles[0]['sources'][0]
    bundles[0]['sources'][0] = bundle_contract.make_source(s['source_id'], s['channel'], s['fragment'], basis=s['basis'], grade=s['evidence_grade'])
    return p31_request.build_request('Synthetic ' + kind + ' protocol', bundles), canonical(d), bundles


class SemanticMappingTests(unittest.TestCase):
    def test_temperature_entity_domain_not_global_absolute_physics_domain(self):
        for value in (16, 17, 26, 29, 30):
            with self.subTest(value=value):
                req, raw, bundles = capability_fixture('SetTemperature', value)
                out = propose_parameterization(req, raw, bundles, input_channel='SYNTHETIC_PROTOCOL')
                self.assertEqual(out['status'], 'PARAMETERIZED_DRAFT')
                self.assertEqual((out['revised_flow']['inputs'][-1]['minimum'], out['revised_flow']['inputs'][-1]['maximum']), (16, 30))
        for value in (15, 31):
            with self.subTest(value=value):
                req, raw, bundles = capability_fixture('SetTemperature', value)
                self.assertEqual(propose_parameterization(req, raw, bundles)['status'], 'DEMONSTRATION_OUT_OF_DOMAIN')

    def test_power_enum_and_object_stay_parameters(self):
        for state in ('on', 'off'):
            with self.subTest(state=state):
                req, raw, bundles = capability_fixture('SetPower', state)
                out = propose_parameterization(req, raw, bundles)
                self.assertEqual(out['status'], 'PARAMETERIZED_DRAFT')
                self.assertEqual(set(out['revised_flow']['inputs'][-1]['choices']), {'on', 'off'})
                self.assertEqual(out['revised_flow']['inputs'][0]['type'], 'entity')
                self.assertNotIn('bedroom_light', canonical(out['revised_flow']))

    def test_brightness_edge_values_keep_same_method_and_fully_approved_domain(self):
        for value in (0, 1, 60, 99, 100):
            with self.subTest(value=value):
                req, raw, bundles = fixtures(with_notes=True)
                d = json.loads(raw)
                for node in (d['candidate_flow']['steps'][2]['argument'], d['candidate_flow']['steps'][3]['predicate']['right'], d['candidate_flow']['goals'][0]['right']):
                    node['value'] = value
                out = propose_parameterization(req, canonical(d), bundles)
                self.assertEqual(out['status'], 'PARAMETERIZED_DRAFT')
                self.assertEqual(out['revised_flow']['inputs'][-1]['maximum'], 100)

    def test_identical_numbers_in_other_entity_never_share_parameter(self):
        req, raw, bundles = fixtures(with_notes=True)
        d = json.loads(raw); f = d['candidate_flow']
        other = copy.deepcopy(f['inputs'][0]); other['name'] = 'other_light'
        f['inputs'].append(other)
        f['allowed_effects'].append({'entity_input': 'other_light', 'property': 'brightnessPercent'})
        f['steps'].append({'id': 'set_other', 'op': 'call', 'entity_input': 'other_light', 'capability': 'SetBrightness',
                           'argument': {'kind': 'literal', 'value': 60}})
        d['parameter_basis'].append({'parameter': 'other_light', 'source_ids': ['fixture.notes'], 'explanation': '另一个合成对象'})
        d['step_basis'].append({'step_id': 'set_other', 'source_ids': ['fixture.notes'], 'explanation': '另一个合成对象'})
        out = propose_parameterization(req, canonical(d), bundles)
        self.assertEqual(out['status'], 'PARAMETERIZED_DRAFT')
        self.assertEqual(out['revised_flow']['steps'][-1]['argument'], {'kind': 'literal', 'value': 60})
        req, bundles = edit_notes(bundles, lambda n: n['parameter_groups'][0]['paths'].append('/steps/4/argument'), req)
        self.assertEqual(analyze(req, canonical(d), bundles)['status'], 'CROSS_ENTITY_OR_PROPERTY_GROUP')

    def test_same_number_different_properties_cannot_share_parameter(self):
        req, raw, bundles = fixtures(with_notes=True)
        req, bundles = edit_notes(bundles, lambda n: n['parameter_groups'][0].update(property='temperatureCelsius'), req)
        self.assertEqual(analyze(req, raw, bundles)['status'], 'CROSS_ENTITY_OR_PROPERTY_GROUP')

    def test_initial_state_protection_never_turns_into_desired_state(self):
        req, raw, bundles = fixtures(with_notes=True)
        d = json.loads(raw); f = d['candidate_flow']
        f['preconditions'].append({'op': 'equals', 'left': {'kind': 'state', 'entity_input': 'light', 'property': 'brightnessPercent'},
                                   'right': {'kind': 'literal', 'value': 60}})
        req, bundles = edit_notes(bundles, lambda n: n['parameter_groups'][0]['paths'].append('/preconditions/1/right'), req)
        self.assertEqual(analyze(req, canonical(d), bundles)['status'], 'PARAMETER_ROLE_UNSUPPORTED')

    def test_user_explicit_sequence_with_same_final_value_is_preserved(self):
        req, raw, bundles = fixtures(with_notes=True)
        d = json.loads(raw); f = d['candidate_flow']
        first = {'id': 'set_first', 'op': 'call', 'capability': 'SetBrightness', 'entity_input': 'light', 'argument': {'kind': 'literal', 'value': 20}}
        f['steps'].insert(2, first)
        d['step_basis'].insert(2, {'step_id': 'set_first', 'source_ids': ['fixture.notes'], 'explanation': '明确先20后60'})
        def change(n):
            n['explicit_order'].insert(2, 'set_first')
            n['step_roles'].insert(2, {'step_id': 'set_first', 'role': 'REQUIRED_BUSINESS', 'reason': '用户显式顺序'})
            n['parameter_groups'][0]['paths'] = ['/steps/3/argument', '/steps/4/predicate/right', '/goals/0/right']
        req, bundles = edit_notes(bundles, change, req)
        out = propose_parameterization(req, canonical(d), bundles)
        self.assertEqual(out['status'], 'PARAMETERIZED_DRAFT')
        self.assertEqual(out['revised_flow']['steps'][2]['argument'], {'kind': 'literal', 'value': 20})
        self.assertEqual(len(out['revised_flow']['steps']), 5)


if __name__ == '__main__': unittest.main()
