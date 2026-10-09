"""Handlers, not names, establish safety; all policy inputs are offline fixtures."""
import unittest
from safe_navigation import SafetyPolicy
from trace_contract import TraceError
from test_support import Harness, node

def policy_fixture():
    return SafetyPolicy([
        {'rule_id': 'rule.open', 'kind': 'CLICK', 'selector': {'resource_id': 'fixture:id/open', 'role': 'button'},
         'effect': 'NO_BUSINESS_WRITE', 'handler_evidence': 'fixture:handler-open-audit',
         'review_cost_ms': None},
        {'rule_id': 'rule.info', 'kind': 'CLICK', 'selector': {'resource_id': 'fixture:id/info', 'role': 'button'},
         'effect': 'NO_BUSINESS_WRITE', 'handler_evidence': 'fixture:handler-info-audit',
         'review_cost_ms': None},
        {'rule_id': 'rule.back', 'kind': 'BACK', 'selector': {'resource_id': 'fixture:id/back', 'role': 'button'},
         'effect': 'NO_BUSINESS_WRITE', 'handler_evidence': 'fixture:handler-back-audit',
         'review_cost_ms': None}])

class SafetyTests(unittest.TestCase):
    def test_policy_uses_handler_evidence_not_navigation_sounding_label(self):
        h = Harness(); h.world._nodes = lambda: [
            node(), node('heading', 'root', role='heading', heading=True, text='Room 101'),
            node('target', 'root', role='button', clickable=True, text='View details', resource_id='fixture:id/danger')]
        result = policy_fixture().candidates(h.observe())
        self.assertEqual(result['items'], [])
        self.assertEqual(result['rejected'][0]['reason'], 'HANDLER_NOT_AUDITED')

    def test_policy_contains_no_target_or_route_and_records_unknown_human_cost(self):
        p = policy_fixture(); exported = p.snapshot()
        self.assertFalse(exported['execution_authority'])
        self.assertEqual(exported['preconfiguration_cost']['known_total_ms'], None)
        self.assertNotIn('target_page', str(exported))
        self.assertNotIn('next_hop', str(exported))
        with self.assertRaises(TraceError):
            SafetyPolicy([dict(exported['rules'][0], target_page='details')])

    def test_duplicate_selector_is_ambiguous_and_never_selects_first(self):
        h = Harness(); h.world.duplicate = True
        result = policy_fixture().candidates(h.observe())
        self.assertEqual(result['items'], [])
        self.assertEqual(result['status'], 'AMBIGUOUS')
        self.assertEqual(result['rejected'][0]['reason'], 'RESOLUTION_AMBIGUOUS')

    def test_switch_slider_editable_and_unknown_effect_never_safe(self):
        for bad in ({'checkable': True}, {'editable': True}, {'role': 'slider',
                     'range': {'min': 0, 'max': 100, 'value': 20, 'kind': 'int'}}):
            with self.subTest(bad=bad):
                h = Harness(); original = h.world._nodes
                h.world._nodes = lambda: [dict(n, **bad) if n['node_local_id'] == 'target' else n for n in original()]
                self.assertFalse(policy_fixture().candidates(h.observe())['items'])
        bad = policy_fixture().snapshot()['rules'][0]; bad['effect'] = 'UNKNOWN'
        self.assertFalse(SafetyPolicy([bad]).candidates(Harness().observe())['items'])

    def test_candidate_is_bound_to_current_observation_and_has_no_authority(self):
        h = Harness(); p = policy_fixture()
        a, b = h.observe(), h.observe()
        ca, cb = p.candidates(a)['items'][0], p.candidates(b)['items'][0]
        self.assertNotEqual(ca['candidate_id'], cb['candidate_id'])
        self.assertEqual(ca['observation_id'], a['observation_id'])
        self.assertFalse(ca['execution_authority'])
        self.assertEqual(ca['semantic_target'], 'Details')
