"""All candidates below are hand-built protocol fixtures, not learnt real business Skills."""
import copy
import json
import unittest
from test_abstraction import fixtures
from p32deps import bundle_contract, canonical, contracts, p31_request
from revision import propose_parameterization


def edit_notes(bundles, callback, req):
    b = copy.deepcopy(bundles)
    s = b[0]['sources'][0]
    callback(s['fragment']['public_flow_notes'])
    b[0]['sources'][0] = bundle_contract.make_source(s['source_id'], s['channel'], s['fragment'],
                                                  basis=s['basis'], grade=s['evidence_grade'])
    return p31_request.build_request(req['goal'], b), b


class RevisionTests(unittest.TestCase):
    def test_parameterize_exact_positions_and_keep_original_order_contract(self):
        req, raw, bundles = fixtures(with_notes=True)
        original = json.loads(raw)['candidate_flow']
        before = copy.deepcopy((req, raw, bundles))
        out = propose_parameterization(req, raw, bundles, input_channel='SYNTHETIC_PROTOCOL')
        self.assertEqual(out['status'], 'PARAMETERIZED_DRAFT')
        f = out['revised_flow']
        self.assertEqual([s['id'] for s in f['steps']], [s['id'] for s in original['steps']])
        for field in ('allowed_effects', 'must_preserve', 'preconditions', 'failure_policy', 'dependencies', 'unknowns', 'verified_scope'):
            self.assertEqual(f[field], original[field])
        self.assertEqual(f['inputs'][-1]['name'], 'percent')
        self.assertEqual(f['steps'][2]['argument'], {'kind': 'input', 'name': 'percent'})
        self.assertEqual(f['steps'][3]['predicate']['right'], {'kind': 'input', 'name': 'percent'})
        self.assertEqual(f['goals'][0]['right'], {'kind': 'input', 'name': 'percent'})
        contracts.validate_document(f)
        self.assertEqual((req, raw, bundles), before)
        self.assertEqual(len(out['revision_diff']), 4)
        self.assertEqual(out['mode'], 'ASSISTED')
        self.assertFalse(out['execution_authority'])
        self.assertFalse(out['ready_for_execution'])
        self.assertEqual(out['verified_parameter_values'], [])

    def test_equal_numbers_are_not_sufficient_evidence(self):
        req, raw, bundles = fixtures()
        out = propose_parameterization(req, raw, bundles)
        self.assertEqual(out['status'], 'PARAMETER_EVIDENCE_UNAVAILABLE')
        self.assertIsNone(out['revised_flow'])

    def test_no_candidate_remains_blocked(self):
        req, _, bundles = fixtures(with_notes=True)
        out = propose_parameterization(req, None, bundles)
        self.assertEqual(out['status'], 'BLOCKED_NO_CANDIDATE')
        self.assertIsNone(out['revised_flow'])

    def test_incomplete_goal_mapping_is_blocked(self):
        req, raw, bundles = fixtures(with_notes=True)
        req, bundles = edit_notes(bundles, lambda n: n['parameter_groups'][0]['paths'].remove('/goals/0/right'), req)
        out = propose_parameterization(req, raw, bundles)
        self.assertEqual(out['status'], 'PARAMETER_GOAL_MAPPING_INCOMPLETE')
        self.assertIsNone(out['revised_flow'])

    def test_verification_for_changed_call_cannot_remain_fixed(self):
        req, raw, bundles = fixtures(with_notes=True)
        req, bundles = edit_notes(bundles, lambda n: n['parameter_groups'][0]['paths'].remove('/steps/3/predicate/right'), req)
        out = propose_parameterization(req, raw, bundles)
        self.assertEqual(out['status'], 'PARAMETER_VERIFICATION_MAPPING_INCOMPLETE')

    def test_single_demo_does_not_establish_domain(self):
        req, raw, bundles = fixtures(with_notes=True)
        req, bundles = edit_notes(bundles, lambda n: n['parameter_groups'][0]['domain'].update(maximum=60), req)
        self.assertEqual(propose_parameterization(req, raw, bundles)['status'], 'PARAMETER_DOMAIN_MISMATCH')

    def test_new_route_or_rule_cost_is_preserved_not_zero_shot(self):
        req, raw, bundles = fixtures(with_notes=True)
        req, bundles = edit_notes(bundles, lambda n: n['assistance'].update(provided_new_route=True, elapsed_seconds=25), req)
        out = propose_parameterization(req, raw, bundles)
        self.assertEqual(out['assistance'][0]['elapsed_seconds'], 25)
        self.assertTrue(out['assistance'][0]['provided_new_route'])
        self.assertFalse(out['automatic_learning_claim'])
        self.assertIsNotNone(out['assistance'][0]['recorded_at_utc'])

    def test_incidental_label_never_deletes_proposed_actions(self):
        req, raw, bundles = fixtures(with_notes=True)
        req, bundles = edit_notes(bundles, lambda n: n['step_roles'][0].update(role='INCIDENTAL'), req)
        out = propose_parameterization(req, raw, bundles)
        self.assertEqual(out['status'], 'PARAMETERIZED_DRAFT')
        self.assertEqual(len(out['revised_flow']['steps']), 4)

    def test_branch_is_not_flattened(self):
        req, raw, bundles = fixtures(with_notes=True)
        req, bundles = edit_notes(bundles, lambda n: n['conditions'].append({'kind': 'BRANCH', 'status': 'REQUIRED', 'description': '需要分支'}), req)
        self.assertEqual(propose_parameterization(req, raw, bundles)['status'], 'UNSUPPORTED_BRANCH')

    def test_order_evidence_conflict_never_sorts_flow(self):
        req, raw, bundles = fixtures(with_notes=True)
        req, bundles = edit_notes(bundles, lambda n: n.update(explicit_order=list(reversed(n['explicit_order']))), req)
        self.assertEqual(propose_parameterization(req, raw, bundles)['status'], 'ORDER_CONFLICT')


if __name__ == '__main__': unittest.main()
