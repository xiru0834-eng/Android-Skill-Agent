import copy
import json
import unittest
from abstraction import analyze
from test_abstraction import fixtures
from p32deps import canonical, digest, bundle_contract, p31_request


def amended(req, bundles, change):
    b = copy.deepcopy(bundles)
    source = b[0]['sources'][0]
    change(source['fragment']['public_flow_notes'])
    b[0]['sources'][0] = bundle_contract.make_source(source['source_id'], source['channel'], source['fragment'],
                                                   basis=source['basis'], grade=source['evidence_grade'])
    return p31_request.build_request(req['goal'], b), b


class AnalysisBoundaryTests(unittest.TestCase):
    def test_recomputed_request_digest_cannot_change_capability_contract(self):
        req, raw, bundles = fixtures(with_notes=True)
        req['allowed_capabilities']['definitions'][0]['maximum'] = 1000
        req['input_digest'] = digest({k: v for k, v in req.items() if k not in ('request_id', 'input_digest')})
        self.assertEqual(analyze(req, raw, bundles)['status'], 'MATERIAL_MISMATCH')

    def test_no_permissions_can_be_inherited_from_draft(self):
        req, raw, bundles = fixtures()
        d = json.loads(raw); d['candidate_flow']['verified_scope'] = ['real_phone_success']
        self.assertEqual(analyze(req, canonical(d), bundles)['status'], 'CANDIDATE_INVALID')
        req['execution_authority'] = True
        self.assertEqual(analyze(req, raw, bundles)['status'], 'INPUT_INTEGRITY_ERROR')

    def test_bad_note_shapes_are_bounded_and_fail_closed(self):
        changes = [lambda n: n.update(extra='ignored?'), lambda n: n['parameter_groups'][0].update(paths=['/steps/999/argument']),
                   lambda n: n['parameter_groups'][0]['domain'].update(step=True),
                   lambda n: n['parameter_groups'][0].update(paths=[]),
                   lambda n: n['assistance'].update(elapsed_seconds=-1),
                   lambda n: n['step_roles'][0].update(role='DELETE_NOW')]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                req, raw, bundles = fixtures(with_notes=True)
                req, bundles = amended(req, bundles, change)
                out = analyze(req, raw, bundles)
                self.assertNotIn(out['status'], ('ANALYZED_DRAFT', 'ANALYZED_DRAFT_WITH_UNKNOWNS'))
                self.assertEqual(out['parameter_source_table'], [])

    def test_wrong_entity_and_unsupported_capability_never_become_generalization(self):
        for entity in ('unknown_lamp', 'host-emulator-5556', 'bedroom_ac'):
            with self.subTest(entity=entity):
                req, raw, bundles = fixtures(with_notes=True)
                req, bundles = amended(req, bundles, lambda n: n['entity_evidence'][0].update(entity_id=entity))
                out = analyze(req, raw, bundles)
                self.assertEqual(out['status'], 'ENTITY_CAPABILITY_MISMATCH')
                self.assertEqual(out['entity_choice_table'], [])

    def test_parameter_unit_range_and_step_must_match_approved_domain(self):
        for change in ({'maximum': 101}, {'minimum': -1}, {'step': 2}, {'unit': 'celsius'}):
            with self.subTest(change=change):
                req, raw, bundles = fixtures(with_notes=True)
                req, bundles = amended(req, bundles, lambda n: n['parameter_groups'][0]['domain'].update(change))
                self.assertEqual(analyze(req, raw, bundles)['status'], 'PARAMETER_DOMAIN_MISMATCH')

    def test_two_claims_cannot_own_same_occurrence(self):
        req, raw, bundles = fixtures(with_notes=True)
        def change(n):
            new = copy.deepcopy(n['parameter_groups'][0]); new['name'] = 'other_percent'
            n['parameter_groups'].append(new)
        req, bundles = amended(req, bundles, change)
        self.assertEqual(analyze(req, raw, bundles)['status'], 'PARAMETER_GROUP_CONFLICT')

    def test_model_or_rule_inference_not_promoted_to_documentary_fact(self):
        for basis in ('MODEL_HYPOTHESIS', 'RULE_INFERENCE', 'UNKNOWN', 'OBSERVATION_FACT'):
            with self.subTest(basis=basis):
                req, raw, bundles = fixtures(with_notes=True, basis=basis)
                out = analyze(req, raw, bundles)
                self.assertEqual(out['parameter_source_table'], [])
                self.assertTrue(any(u['code'] == 'UNVERIFIED_SUPPLEMENT' for u in out['unknowns']))

    def test_uncited_supplement_and_step_source_are_not_accepted(self):
        req, raw, bundles = fixtures(with_notes=True)
        # Source is real in this fixture but no longer cited by the candidate.
        extra = bundle_contract.make_source('fixture.other', 'SYNTHETIC_PROTOCOL', {'text': 'other'},
            basis='DOCUMENTATION_STATEMENT', grade='SYNTHETIC_PROTOCOL_NOT_REAL_MODEL')
        bundles[0]['sources'].append(extra)
        req = p31_request.build_request(req['goal'], bundles)
        d = json.loads(raw); d['candidate_flow']['evidence_refs'] = ['fixture.other']
        self.assertEqual(analyze(req, canonical(d), bundles)['status'], 'SUPPLEMENT_NOT_CITED')
        d['candidate_flow']['evidence_refs'] = ['fixture.notes']
        d['step_basis'][0]['source_ids'] = ['fixture.other']
        self.assertEqual(analyze(req, canonical(d), bundles)['status'], 'ROLE_SOURCE_NOT_CITED')

    def test_requirement_not_supported_by_ordered_grammar_stays_review_required(self):
        for kind in ('SUBMISSION', 'PRECONDITION'):
            req, raw, bundles = fixtures(with_notes=True)
            req, bundles = amended(req, bundles, lambda n: n['conditions'].append({'kind': kind, 'status': 'REQUIRED', 'description': '新规则，未证实'}))
            self.assertEqual(analyze(req, raw, bundles)['status'], 'REQUIRES_CONDITION_REVIEW')


if __name__ == '__main__': unittest.main()
