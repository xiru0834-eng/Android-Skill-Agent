import copy
import json
import unittest
from test_abstraction import fixtures
from p32deps import bundle_contract, canonical, p31_request
from abstraction import analyze
from revision import propose_parameterization


class ReviewGapTests(unittest.TestCase):
    def test_shared_identical_source_across_bundles_is_not_double_counted(self):
        req, raw, bundles = fixtures(with_notes=True)
        other = bundle_contract.make_bundle(bundles[0]['environment'], mode='SYNTHETIC_PROTOCOL')
        other['sources'] = copy.deepcopy(bundles[0]['sources'])
        bundles.append(other)
        req = p31_request.build_request(req['goal'], bundles)
        out = propose_parameterization(req, raw, bundles)
        self.assertEqual(out['status'], 'PARAMETERIZED_DRAFT')
        self.assertEqual(len(out['parameter_source_table']), 1)
        self.assertEqual(len(out['assistance']), 1)

    def test_existing_parameterized_candidate_is_analyzed_not_ignored(self):
        req, raw, bundles = fixtures(with_notes=True)
        d = json.loads(raw); f = d['candidate_flow']
        f['inputs'].append({'name': 'percent', 'type': 'integer', 'minimum': 0, 'maximum': 100,
                            'step': 1, 'unit': 'percent', 'default_rule': 'REQUIRE_EXPLICIT'})
        for node in (f['steps'][2]['argument'], f['steps'][3]['predicate']['right'], f['goals'][0]['right']):
            node.clear(); node.update(kind='input', name='percent')
        d['parameter_basis'].append({'parameter': 'percent', 'source_ids': ['fixture.notes'], 'explanation': '已有参数候选'})
        out = propose_parameterization(req, canonical(d), bundles)
        self.assertEqual(out['status'], 'PARAMETERIZED_DRAFT_UNCHANGED')
        self.assertEqual(out['revised_flow'], f)
        self.assertEqual(out['revision_diff'], [])
        self.assertEqual(out['existing_parameter_source_table'][0]['occurrence_paths'],
                         ['/steps/2/argument', '/steps/3/predicate/right', '/goals/0/right'])

    def test_existing_candidate_domain_without_evidence_stays_declared_only(self):
        req, raw, bundles = fixtures()
        d = json.loads(raw); f = d['candidate_flow']
        f['inputs'].append({'name': 'percent', 'type': 'integer', 'minimum': 0, 'maximum': 100,
                            'step': 1, 'unit': 'percent', 'default_rule': 'REQUIRE_EXPLICIT'})
        for node in (f['steps'][2]['argument'], f['steps'][3]['predicate']['right'], f['goals'][0]['right']):
            node.clear(); node.update(kind='input', name='percent')
        d['parameter_basis'].append({'parameter': 'percent', 'source_ids': ['fixture.notes'], 'explanation': '候选参数声明'})
        out = analyze(req, canonical(d), bundles)
        self.assertEqual(out['existing_parameter_source_table'][0]['evidence_status'], 'CANDIDATE_DECLARATION_ONLY')
        self.assertTrue(any(u['code'] == 'PARAMETER_DOMAIN_EVIDENCE_UNKNOWN' for u in out['unknowns']))

    def test_unknown_entity_inputs_remain_explicit_even_if_other_entity_is_documented(self):
        req, raw, bundles = fixtures(with_notes=True)
        d = json.loads(raw); f = d['candidate_flow']
        f['inputs'].append({'name': 'other_entity', 'type': 'entity', 'default_rule': 'REQUIRE_EXPLICIT', 'required_capabilities': ['SetPower']})
        d['parameter_basis'].append({'parameter': 'other_entity', 'source_ids': ['fixture.notes'], 'explanation': '未确认对象'})
        out = analyze(req, canonical(d), bundles)
        self.assertTrue(any(u['code'] == 'ENTITY_GENERALIZATION_UNKNOWN' and 'other_entity' in u['description'] for u in out['unknowns']))

    def test_unclassified_channel_cannot_be_arbitrary_claim(self):
        req, raw, bundles = fixtures(with_notes=True)
        self.assertEqual(analyze(req, raw, bundles, input_channel='LIVE_ANDROID_SUCCESS')['status'], 'INPUT_CHANNEL_INVALID')


if __name__ == '__main__': unittest.main()
