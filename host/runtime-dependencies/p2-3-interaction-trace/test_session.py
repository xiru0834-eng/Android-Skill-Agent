"""Controlled trajectory tests. All dispatches and models are explicit local fakes."""
import copy
from dataclasses import replace
import unittest
from interaction_trace import TraceSession, native_readiness
from trace_contract import TraceError
from p23deps import derive_page
from test_support import Harness, action, receipt, write_audit, scope_fixture
from test_safety import policy_fixture

class FakeChooser:
    channel = 'FAKE_MODEL'
    def __init__(self, fn=None):
        self.fn = fn
        self.calls = 0
    def choose(self, observation, candidates):
        self.calls += 1
        if self.fn:
            return self.fn(observation, candidates)
        return {'observation_id': observation['observation_id'], 'candidate_id': candidates[0]['candidate_id']}

def session(h, **changes):
    args = {'scope': h.scope, 'authorization': h.auth, 'budget': h.budget,
            'clock': h.clock, 'policy': policy_fixture(), 'enabled': True}
    args.update(changes)
    return TraceSession(**args)

class SessionTests(unittest.TestCase):
    def test_safe_step_reobserves_before_input_and_records_actual_dispatch(self):
        h = Harness(); target = h.target(h.observe('details')); h.world.page = 'home'
        s = session(h)
        result = s.navigate_one(h.world, target=target)
        self.assertEqual(result['status'], 'ARRIVAL_VERIFIED_SIMULATED')
        self.assertEqual(len(h.world.dispatches), 1)
        self.assertGreaterEqual(h.world.tree_reads, 8)
        bundle = s.bundle()
        self.assertEqual(len(bundle['interactions']), 1)
        self.assertEqual(bundle['map']['verified_simulated_edges'], 1)
        self.assertEqual(bundle['map']['real_verified_edges'], 0)
        self.assertNotEqual(result['planning_observation_id'], result['before_observation_id'])

    def test_already_at_target_has_observation_but_no_action_or_new_edge(self):
        h = Harness(); goal = h.target(h.observe('home')); s = session(h)
        result = s.navigate_one(h.world, target=goal)
        self.assertEqual(result['status'], 'ALREADY_AT_TARGET')
        self.assertFalse(h.world.dispatches)
        self.assertEqual(s.graph.snapshot()['edges'], [])
        self.assertGreater(h.budget.snapshot()['spent']['observations'], 1)

    def test_recorded_human_and_evaluator_sources_do_not_become_agent_counts(self):
        h = Harness(); s = session(h)
        a, b = h.observe('home'), h.observe('details')
        s.record_interaction('HUMAN_DEMONSTRATION', a, b, action(), receipt(a, b, status='OBSERVED_INPUT_SIMULATED'),
                             write_audit(), expected_target=h.target(b))
        c, d = h.observe('details'), h.observe('info')
        s.record_interaction('EVALUATOR_INITIALIZATION', c, d, action(), receipt(c, d),
                             write_audit(), expected_target=h.target(d))
        stats = s.bundle()['source_counts']
        self.assertEqual(stats['HUMAN_DEMONSTRATION'], 1)
        self.assertEqual(stats['EVALUATOR_INITIALIZATION'], 1)
        self.assertEqual(stats['AGENT_NAVIGATION'], 0)
        self.assertEqual(s.graph.snapshot()['verified_simulated_edges'], 1)

    def test_unknown_or_pending_effect_stops_and_is_not_verified(self):
        for audit in (write_audit(coverage='UNAVAILABLE'), write_audit(pending=1), write_audit(committed=1)):
            with self.subTest(audit=audit):
                h = Harness(); goal = h.target(h.observe('details')); h.world.page = 'home'; h.world.audit = audit
                s = session(h); result = s.navigate_one(h.world, target=goal)
                self.assertNotEqual(result['status'], 'ARRIVAL_VERIFIED_SIMULATED')
                self.assertEqual(s.graph.snapshot()['verified_simulated_edges'], 0)
                self.assertNotEqual(s.state, 'RUNNING')

    def test_cancel_before_start_does_not_capture_or_dispatch(self):
        h = Harness(); s = session(h); s.cancel()
        result = s.navigate_one(h.world)
        self.assertEqual(result['status'], 'CANCELLED')
        self.assertEqual(h.world.tree_reads, 0)
        self.assertEqual(h.world.dispatches, [])

    def test_cancel_after_dispatched_action_does_not_undo_or_resume(self):
        h = Harness(); s = session(h); h.world.after_dispatch = s.cancel
        result = s.navigate_one(h.world)
        self.assertEqual(result['status'], 'CANCELLED')
        self.assertEqual(h.world.page, 'details')
        self.assertEqual(len(h.world.dispatches), 1)
        self.assertIsNone(s.bundle()['interactions'][0]['after'])
        s.navigate_one(h.world)
        self.assertEqual(len(h.world.dispatches), 1)

    def test_late_receipt_is_only_diagnostic_never_reactivates(self):
        h = Harness(); s = session(h); h.world.after_dispatch = s.cancel
        s.navigate_one(h.world)
        dispatch_id = s.bundle()['interactions'][0]['dispatch']['dispatch_id']
        s.note_late_callback(dispatch_id)
        self.assertEqual(s.state, 'CANCELLED')
        self.assertEqual(s.graph.snapshot()['verified_simulated_edges'], 0)
        self.assertEqual(s.bundle()['diagnostics'][-1]['event'], 'LATE_CALLBACK_IGNORED')

    def test_fabricated_stale_extra_model_candidates_rejected_and_requests_charged(self):
        bads = [
            lambda o, c: {'observation_id': o['observation_id'], 'candidate_id': 'made.up'},
            lambda o, c: {'observation_id': 'old.observation', 'candidate_id': c[0]['candidate_id']},
            lambda o, c: {'observation_id': o['observation_id'], 'candidate_id': c[0]['candidate_id'], 'approved': True}]
        for fn in bads:
            with self.subTest(fn=fn):
                h = Harness(); s = session(h); model = FakeChooser(fn)
                result = s.navigate_one(h.world, proposal=model)
                self.assertEqual(result['status'], 'REJECTED')
                self.assertEqual(h.budget.snapshot()['spent']['model_requests'], 1)
                self.assertFalse(h.world.dispatches)

    def test_model_error_wait_and_replanning_share_one_budget(self):
        h = Harness(); s = session(h)
        def error(o, c):
            h.clock.advance(100)
            raise RuntimeError('untrusted model text')
        s.navigate_one(h.world, proposal=FakeChooser(error))
        first = h.budget.snapshot()
        s.navigate_one(h.world, proposal=FakeChooser(lambda o, c: {'bad': 1}))
        second = h.budget.snapshot()
        self.assertEqual(first['session_id'], second['session_id'])
        self.assertEqual(second['spent']['model_requests'], 2)
        self.assertGreater(second['spent']['observations'], first['spent']['observations'])

    def test_budget_exhaustion_stops_replans_without_new_dispatch(self):
        scope = scope_fixture()
        scope['budgets']['max_actions'] = 1
        h = Harness(scope); s = session(h)
        s.navigate_one(h.world)
        result = s.navigate_one(h.world)
        self.assertEqual(result['status'], 'BUDGET_EXCEEDED')
        self.assertEqual(len(h.world.dispatches), 1)
        self.assertEqual(h.budget.snapshot()['spent']['actions'], 1)

    def test_scope_environment_or_budget_instance_change_cannot_reset(self):
        for change in ('scope', 'budget'):
            with self.subTest(change=change):
                h = Harness(); s = session(h)
                if change == 'scope':
                    s.scope['target']['ui_revision'] = 'u2'
                else:
                    from p23deps import LearningBudget
                    s.budget = LearningBudget(h.scope, clock=h.clock)
                result = s.navigate_one(h.world)
                self.assertIn(result['status'], ('SCOPE_CHANGED', 'BUDGET_SESSION_CHANGED'))
                self.assertFalse(h.world.dispatches)

    def test_missing_authority_or_native_claim_is_rejected_without_reading_android(self):
        h = Harness()
        for args in ({'authorization': None}, {'channel': 'REAL_ANDROID'}, {'enabled': False}):
            with self.subTest(args=args), self.assertRaises(TraceError):
                session(h, **args)
        self.assertEqual(native_readiness()['status'], 'BLOCKED')
        self.assertFalse(h.world.dispatches)

    def test_paid_model_is_not_invoked_by_optional_proposal_interface(self):
        h = Harness(); s = session(h)
        model = FakeChooser(); model.channel = 'REAL_MODEL'
        result = s.navigate_one(h.world, proposal=model)
        self.assertEqual(result['status'], 'REJECTED')
        self.assertEqual(model.calls, 0)
        self.assertEqual(h.budget.snapshot()['spent']['model_requests'], 0)

    def test_unexpected_popup_blocks_before_dispatch(self):
        h = Harness(); h.world.popup = 'unknown.popup'; s = session(h)
        result = s.navigate_one(h.world)
        self.assertEqual(result['status'], 'BLOCKED_BY_OVERLAY')
        self.assertFalse(h.world.dispatches)

    def test_no_effect_gets_finite_reobserve_not_false_success(self):
        h = Harness(); goal = h.target(h.observe('details')); h.world.page = 'home'; h.world.no_effect = True
        s = session(h); result = s.navigate_one(h.world, target=goal)
        self.assertEqual(result['status'], 'UNCONFIRMED')
        self.assertEqual(len(h.world.dispatches), 1)
        self.assertLessEqual(result['post_observations'], 4)
        self.assertEqual(s.graph.snapshot()['verified_simulated_edges'], 0)

    def test_changed_page_during_model_selection_stops_old_plan(self):
        h = Harness(); s = session(h)
        def choose(o, c):
            result = {'observation_id': o['observation_id'], 'candidate_id': c[0]['candidate_id']}
            h.world.page = 'unrelated'
            return result
        result = s.navigate_one(h.world, proposal=FakeChooser(choose))
        self.assertEqual(result['status'], 'PLANNING_OBSERVATION_CHANGED')
        self.assertFalse(h.world.dispatches)

    def test_unknown_side_effect_after_recording_cannot_be_queried_as_success(self):
        h = Harness(); s = session(h); h.world.audit = write_audit(coverage='UNAVAILABLE')
        result = s.navigate_one(h.world)
        self.assertEqual(result['status'], 'UNCONFIRMED')
        self.assertIn('BUSINESS_EFFECT_UNKNOWN', s.bundle()['interactions'][0]['unknowns'])

    def test_double_step_source_order_and_dispatch_ids_preserved(self):
        h = Harness(); s = session(h)
        s.navigate_one(h.world)
        s.navigate_one(h.world)
        steps = s.bundle()['interactions']
        self.assertEqual(len(steps), 2)
        self.assertNotEqual(steps[0]['dispatch']['dispatch_id'], steps[1]['dispatch']['dispatch_id'])
        self.assertEqual(steps[0]['after']['page']['page_instance_id'], steps[1]['before']['page']['page_instance_id'])
