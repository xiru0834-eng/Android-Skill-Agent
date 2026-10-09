"""Deterministic offline graph search; no inferred reverse or invented links."""
import unittest
from navigation_graph import NavigationGraph
from trace_contract import make_interaction
from p23deps import derive_page
from test_support import Harness, action, receipt, write_audit


class GraphTests(unittest.TestCase):
    def edge(self, graph, h, start='home', end='details', **options):
        a, b = h.observe(start), h.observe(end)
        step = make_interaction('AGENT_NAVIGATION', a, b, action(local='target'),
                                receipt(a, b), write_audit(), entity_types=['room'],
                                expected_target=h.target(b), **options)
        return graph.add_interaction(step, a, b), a, b

    def test_verified_edge_keeps_actual_before_after_and_dispatch_references(self):
        graph = NavigationGraph(['room']); h = Harness()
        edge, a, b = self.edge(graph, h)
        self.assertEqual(edge['status'], 'VERIFIED_SIMULATED')
        self.assertEqual(edge['evidence']['before_observation_id'], a['observation_id'])
        self.assertEqual(edge['evidence']['after_observation_id'], b['observation_id'])
        self.assertFalse(edge['execution_authority'])
        self.assertEqual(graph.snapshot()['real_verified_edges'], 0)

    def test_forward_does_not_create_reverse_edge(self):
        graph = NavigationGraph(['room']); h = Harness()
        _, a, b = self.edge(graph, h)
        found = graph.search(derive_page(a, entity_types=['room']), h.target(b))
        absent = graph.search(derive_page(b, entity_types=['room']), h.target(a))
        self.assertEqual(found['status'], 'FOUND')
        self.assertEqual(absent['status'], 'NO_KNOWN_PATH')

    def test_hypothesis_and_unconfirmed_transitions_are_not_search_paths(self):
        graph = NavigationGraph(['room']); h = Harness()
        a, b = h.observe('home'), h.observe('details')
        graph.add_hypothesis(derive_page(a, entity_types=['room']), h.target(b), 'model.fixture')
        step = make_interaction('AGENT_NAVIGATION', a, b, action(), receipt(a, b),
                                write_audit(coverage='UNAVAILABLE'), entity_types=['room'],
                                expected_target=h.target(b))
        graph.add_interaction(step, a, b)
        self.assertEqual(graph.search(derive_page(a, entity_types=['room']), h.target(b))['status'], 'NO_KNOWN_PATH')
        self.assertEqual(graph.snapshot()['verified_simulated_edges'], 0)

    def test_no_transition_and_evaluator_do_not_create_navigation_edges(self):
        graph = NavigationGraph(['room']); h = Harness()
        a, b = h.observe('home'), h.observe('home')
        step = make_interaction('AGENT_NAVIGATION', a, b, action(), receipt(a, b), write_audit(),
                                entity_types=['room'], expected_target=h.target(b))
        self.assertIsNone(graph.add_interaction(step, a, b))
        c = h.observe('details')
        step = make_interaction('EVALUATOR_INITIALIZATION', b, c, action(), receipt(b, c), write_audit(),
                                entity_types=['room'], expected_target=h.target(c))
        self.assertIsNone(graph.add_interaction(step, b, c))

    def test_bfs_is_deterministic_terminates_on_cycles_and_finds_two_steps(self):
        graph = NavigationGraph(['room']); h = Harness()
        _, a, b = self.edge(graph, h)
        _, _, c = self.edge(graph, h, 'details', 'info')
        self.edge(graph, h, 'info', 'details')
        first = graph.search(derive_page(a, entity_types=['room']), h.target(c))
        second = graph.search(derive_page(a, entity_types=['room']), h.target(c))
        self.assertEqual(first, second)
        self.assertEqual(first['status'], 'FOUND')
        self.assertEqual(len(first['edges']), 2)
        goal = h.observe('unrelated')
        self.assertEqual(graph.search(derive_page(a, entity_types=['room']), h.target(goal))['status'], 'NO_KNOWN_PATH')

    def test_invalidated_edge_preserves_history_and_no_longer_searches(self):
        graph = NavigationGraph(['room']); h = Harness()
        edge, a, b = self.edge(graph, h)
        graph.invalidate(edge['edge_id'], 'ARRIVAL_MISMATCH')
        snap = graph.snapshot()
        self.assertEqual(snap['edges'][0]['status'], 'INVALIDATED')
        self.assertEqual(snap['edges'][0]['history'][0]['status'], 'VERIFIED_SIMULATED')
        self.assertEqual(graph.search(derive_page(a, entity_types=['room']), h.target(b))['status'], 'NO_KNOWN_PATH')

    def test_environment_host_and_entry_context_are_not_combined(self):
        graph = NavigationGraph(['room']); h = Harness()
        _, a, b = self.edge(graph, h)
        wrong = derive_page(a, entity_types=['room'])
        wrong['environment']['ui_revision'] = 'different'
        self.assertEqual(graph.search(wrong, h.target(b))['status'], 'NO_KNOWN_PATH')
        h.world.entry = 'secondary.entry'
        same_template_different_entry = h.observe('home')
        self.assertEqual(graph.search(derive_page(same_template_different_entry, entity_types=['room']),
                                      h.target(b))['status'], 'NO_KNOWN_PATH')

    def test_observed_fixture_back_operation_requires_separate_evidence(self):
        graph = NavigationGraph(['room']); h = Harness()
        _, home, details = self.edge(graph, h)
        start, end = h.observe('info'), h.observe('details')
        step = make_interaction('HUMAN_DEMONSTRATION', start, end,
                                action('BACK', 'Back to details'), receipt(start, end, status='OBSERVED_INPUT_SIMULATED'),
                                write_audit(), entity_types=['room'], expected_target=h.target(end))
        graph.add_interaction(step, start, end)
        self.assertEqual(graph.search(derive_page(start, entity_types=['room']), h.target(end))['status'], 'FOUND')
        self.assertEqual(graph.search(derive_page(details, entity_types=['room']), h.target(home))['status'], 'NO_KNOWN_PATH')
