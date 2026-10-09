"""Contract-first RED: synthetic evidence, never Android or a model."""
import copy
import unittest
from trace_contract import TraceError, make_interaction, validate_interaction
from test_support import Harness, action, receipt, write_audit


class TraceContractTests(unittest.TestCase):
    def test_all_sources_stay_separate_and_only_safe_navigation_can_verify(self):
        h = Harness()
        before, after = h.observe('home'), h.observe('details')
        for source in ('HUMAN_DEMONSTRATION', 'AGENT_NAVIGATION',
                       'AGENT_BUSINESS_EXECUTION', 'EVALUATOR_INITIALIZATION', 'UNKNOWN'):
            with self.subTest(source=source):
                step = make_interaction(source, before, after, action(), receipt(before, after),
                                        write_audit(), entity_types=['room'], expected_target=h.target(after))
                self.assertEqual(step['source'], source)
                self.assertFalse(step['execution_authority'])
                self.assertEqual(step['before']['observation_id'], before['observation_id'])
                self.assertEqual(step['after']['observation_id'], after['observation_id'])
                self.assertEqual(step['public_clues']['resource_id'], 'fixture:id/open')
                eligible = source in ('HUMAN_DEMONSTRATION', 'AGENT_NAVIGATION')
                self.assertEqual(step['status'] == 'ARRIVAL_VERIFIED_SIMULATED', eligible)
                self.assertEqual(validate_interaction(step, before, after, ['room']), step)

    def test_no_transition_is_not_a_verified_edge_even_when_already_at_goal(self):
        h = Harness()
        before, after = h.observe('home'), h.observe('home')
        step = make_interaction('AGENT_NAVIGATION', before, after, action(),
                                receipt(before, after), write_audit(),
                                entity_types=['room'], expected_target=h.target(after))
        self.assertEqual(step['status'], 'NO_TRANSITION')
        self.assertFalse(step['changes']['page_changed'])

    def test_side_effects_unknown_or_pending_cannot_verify(self):
        h = Harness()
        before, after = h.observe('home'), h.observe('details')
        for audit in (write_audit(committed=1), write_audit(pending=1), write_audit(coverage='UNAVAILABLE')):
            with self.subTest(audit=audit):
                step = make_interaction('AGENT_NAVIGATION', before, after, action(),
                                        receipt(before, after), audit, entity_types=['room'],
                                        expected_target=h.target(after))
                self.assertNotEqual(step['status'], 'ARRIVAL_VERIFIED_SIMULATED')
                self.assertIn(step['status'], ('UNCONFIRMED', 'SAFETY_VIOLATION'))

    def test_made_up_or_stale_node_and_untrusted_fields_rejected(self):
        h = Harness()
        before, after = h.observe('home'), h.observe('details')
        bad = action(); bad['node_local_id'] = 'old-node'
        with self.assertRaises(TraceError):
            make_interaction('AGENT_NAVIGATION', before, after, bad, receipt(before, after),
                             write_audit(), entity_types=['room'])
        bad = action(); bad['approved'] = True
        with self.assertRaises(TraceError):
            make_interaction('AGENT_NAVIGATION', before, after, bad, receipt(before, after),
                             write_audit(), entity_types=['room'])

    def test_dispatch_clock_not_interchangeable_with_legacy_event_time(self):
        h = Harness()
        before, after = h.observe('home'), h.observe('details')
        bad = receipt(before, after); bad['clock_domain'] = 'uptimeMillis'
        with self.assertRaises(TraceError):
            make_interaction('HUMAN_DEMONSTRATION', before, after, action(), bad,
                             write_audit(), entity_types=['room'])

    def test_not_sent_or_unknown_dispatch_never_verifies(self):
        h = Harness()
        before, after = h.observe('home'), h.observe('details')
        for status in ('NOT_SENT', 'UNKNOWN'):
            with self.subTest(status=status):
                step = make_interaction('AGENT_NAVIGATION', before, after, action(),
                                        receipt(before, after, status=status), write_audit(),
                                        entity_types=['room'], expected_target=h.target(after))
                self.assertEqual(step['status'], 'UNCONFIRMED')

    def test_missing_after_observation_preserves_unknown_outcome(self):
        h = Harness(); before = h.observe('home')
        step = make_interaction('HUMAN_DEMONSTRATION', before, None, action(),
                                receipt(before, None), write_audit(coverage='UNAVAILABLE'),
                                entity_types=['room'])
        self.assertEqual(step['status'], 'UNCONFIRMED')
        self.assertIsNone(step['after'])

    def test_tampered_status_or_delta_cannot_survive_validation(self):
        h = Harness(); before, after = h.observe('home'), h.observe('details')
        step = make_interaction('AGENT_NAVIGATION', before, after, action(),
                                receipt(before, after), write_audit(coverage='UNAVAILABLE'),
                                entity_types=['room'], expected_target=h.target(after))
        for key, value in (('status', 'ARRIVAL_VERIFIED_SIMULATED'), ('source', 'ADMIN')):
            bad = copy.deepcopy(step); bad[key] = value
            with self.subTest(key=key), self.assertRaises(TraceError):
                validate_interaction(bad, before, after, ['room'])


if __name__ == '__main__':
    unittest.main()
