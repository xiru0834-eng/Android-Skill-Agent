"""Synthetic protocol fixtures only; never evidence of GPT learning or real UI execution."""
import copy
import json
from pathlib import Path
import unittest
from abstraction import analyze
from p32deps import bundle_contract, canonical, p31_request, contracts


def fixtures(*, with_notes=False, basis='DOCUMENTATION_STATEMENT'):
    b = bundle_contract.make_bundle({'app_package': 'edu.sydney.parameterroom', 'app_build': '6',
        'environment_id': 'synthetic-protocol', 'ui_revision': 'synthetic-v1', 'domain': 'EXPERIMENT_APP'}, mode='SYNTHETIC_PROTOCOL')
    notes = {'schema_version': '1.0', 'entity_evidence': [{'entity_input': 'light', 'entity_id': 'bedroom_light',
        'identity_basis': 'PUBLIC_DOCUMENT', 'supported_capabilities': ['SetPower', 'SetBrightness']}],
        'parameter_groups': [{'name': 'percent', 'paths': ['/steps/2/argument', '/steps/3/predicate/right', '/goals/0/right'],
          'entity_input': 'light', 'property': 'brightnessPercent', 'reason': '同一灯的目标亮度',
          'domain': {'type': 'integer', 'minimum': 0, 'maximum': 100, 'step': 1, 'unit': 'percent'},
          'domain_basis': 'APPROVED_ENTITY_CAPABILITY'}],
        'step_roles': [{'step_id': 'read_power', 'role': 'PROTECTION', 'reason': '读取待保持状态'},
          {'step_id': 'check_power', 'role': 'PROTECTION', 'reason': '保护状态必须已知'},
          {'step_id': 'set_brightness', 'role': 'REQUIRED_BUSINESS', 'reason': '目标属性'},
          {'step_id': 'check_brightness', 'role': 'VERIFICATION', 'reason': '核验目标'}],
        'explicit_order': ['read_power', 'check_power', 'set_brightness', 'check_brightness'],
        'conditions': [], 'assistance': {'actor': 'fixture.expert', 'reason': '合成资料说明', 'elapsed_seconds': 12,
          'provided_new_rules': True, 'provided_new_route': False}}
    fragment = {'text': 'SYNTHETIC PROTOCOL ONLY: explicit public documentation, not a real model experiment'}
    if with_notes: fragment['public_flow_notes'] = notes
    source = bundle_contract.make_source('fixture.notes', 'SYNTHETIC_PROTOCOL', fragment,
        basis=basis, grade='SYNTHETIC_PROTOCOL_NOT_REAL_MODEL')
    b['sources'] = [source]
    request = p31_request.build_request('学习亮度方法，保持电源 / learn brightness preserving power', [b])
    f = json.loads(Path('D:/Codex-deliveries/smarthome-ui-polish/p1-2-flow-contracts/examples/valid-flow.json').read_text(encoding='utf-8'))
    f['inputs'] = [f['inputs'][0]]
    for path in (f['steps'][2]['argument'], f['steps'][3]['predicate']['right'], f['goals'][0]['right']):
        path.clear(); path.update(kind='literal', value=60)
    f['evidence_refs'] = ['fixture.notes']
    draft = {'status': 'PROPOSED', 'candidate_flow': f,
        'parameter_basis': [{'parameter': 'light', 'source_ids': ['fixture.notes'], 'explanation': '合成对象声明'}],
        'step_basis': [{'step_id': s['id'], 'source_ids': ['fixture.notes'], 'explanation': '合成协议来源'} for s in f['steps']],
        'uncertainties': [], 'unsupported_capabilities': [], 'questions': []}
    return request, canonical(draft), [b]


class AnalysisTests(unittest.TestCase):
    def test_literal_occurrences_are_separate_and_dont_infer_range(self):
        req, draft, bundles = fixtures()
        out = analyze(req, draft, bundles, input_channel='SYNTHETIC_PROTOCOL')
        rows = [r for r in out['occurrences'] if r['value_kind'] == 'literal']
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({r['occurrence_id'] for r in rows}), 3)
        self.assertTrue(all(r['domain']['demonstration_proves_domain'] is False for r in rows))
        self.assertFalse(out['execution_authority'])
        self.assertTrue(any(u['code'] == 'PARAMETER_GROUPING_UNKNOWN' for u in out['unknowns']))

    def test_approved_domain_and_declared_parameter_mapping_are_distinct(self):
        req, draft, bundles = fixtures(with_notes=True)
        out = analyze(req, draft, bundles, input_channel='SYNTHETIC_PROTOCOL')
        group = out['parameter_source_table'][0]
        self.assertEqual(group['parameter'], 'percent')
        self.assertEqual(group['evidence_status'], 'DOCUMENTED_NOT_EXECUTION_VERIFIED')
        self.assertEqual(group['domain']['maximum'], 100)
        self.assertEqual(len(group['occurrence_paths']), 3)
        self.assertEqual(out['mode'], 'ASSISTED')

    def test_missing_candidate_is_blocked_not_filled_with_test_answer(self):
        req, _, bundles = fixtures()
        out = analyze(req, None, bundles, input_channel='NO_MODEL_CALL')
        self.assertEqual(out['status'], 'BLOCKED_NO_CANDIDATE')
        self.assertIsNone(out['candidate_flow'])
        self.assertEqual(out['parameter_source_table'], [])

    def test_wrong_material_digest_and_request_tampering_are_rejected(self):
        req, draft, bundles = fixtures()
        wrong = copy.deepcopy(bundles); wrong[0]['scope_summary']['limitations'].append('changed')
        self.assertEqual(analyze(req, draft, wrong)['status'], 'MATERIAL_MISMATCH')
        req['goal'] = 'changed'
        self.assertEqual(analyze(req, draft, bundles)['status'], 'INPUT_INTEGRITY_ERROR')

    def test_model_notes_are_hypotheses_not_facts(self):
        req, draft, bundles = fixtures(with_notes=True, basis='MODEL_HYPOTHESIS')
        out = analyze(req, draft, bundles, input_channel='SYNTHETIC_PROTOCOL')
        self.assertEqual(out['parameter_source_table'], [])
        self.assertTrue(any(u['code'] == 'UNVERIFIED_SUPPLEMENT' for u in out['unknowns']))

    def test_step_roles_protection_and_verification_keep_their_meaning(self):
        req, draft, bundles = fixtures(with_notes=True)
        out = analyze(req, draft, bundles)
        self.assertEqual([s['role'] for s in out['fixed_variable_unknown_steps']],
                         ['PROTECTION', 'PROTECTION', 'REQUIRED_BUSINESS', 'VERIFICATION'])
        self.assertTrue(all(s['necessity_basis'] == 'DOCUMENTATION_STATEMENT' for s in out['fixed_variable_unknown_steps']))

    def test_unknown_submission_and_branch_never_become_known(self):
        req, draft, bundles = fixtures(with_notes=True)
        b = bundles[0]
        n = b['sources'][0]['fragment']['public_flow_notes']
        n['conditions'] = [{'kind': 'BRANCH', 'status': 'REQUIRED', 'description': '根据状态走不同分支'},
                           {'kind': 'SUBMISSION', 'status': 'UNKNOWN', 'description': '不知道是否必须保存'}]
        s = b['sources'][0]
        b['sources'][0] = bundle_contract.make_source(s['source_id'], s['channel'], s['fragment'], basis=s['basis'], grade=s['evidence_grade'])
        req = p31_request.build_request(req['goal'], bundles)
        out = analyze(req, draft, bundles)
        self.assertEqual(out['status'], 'UNSUPPORTED_BRANCH')
        self.assertIsNone(out['revised_flow'])
        self.assertTrue(any(u['code'] == 'SUBMISSION_UNKNOWN' for u in out['unknowns']))

    def test_primitive_branch_in_candidate_is_rejected(self):
        req, draft, bundles = fixtures()
        value = json.loads(draft); value['candidate_flow']['steps'][0]['op'] = 'if'
        out = analyze(req, canonical(value), bundles)
        self.assertEqual(out['status'], 'CANDIDATE_INVALID')


if __name__ == '__main__': unittest.main()
