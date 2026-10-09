"""Adversarial cases for shared budgets and truthful dispatch evidence (offline)."""
import copy
import threading
import unittest
from trace_contract import TraceError, make_interaction
from test_support import Harness, action, receipt, write_audit, node, scope_fixture
from test_session import session, FakeChooser
from p23deps import derive_page

class HardeningTests(unittest.TestCase):
    def learned(self):
        h = Harness(); s = session(h)
        a, b, c = h.observe('home'), h.observe('details'), h.observe('info')
        s.record_interaction('HUMAN_DEMONSTRATION', a, b, action(), receipt(a,b), write_audit(), expected_target=h.target(b))
        s.record_interaction('HUMAN_DEMONSTRATION', b, c, action(), receipt(b,c), write_audit(), expected_target=h.target(c))
        h.world.page = 'home'
        return h,s,h.target(c)

    def test_known_two_step_route_search_has_zero_model_calls_and_fresh_dispatch(self):
        h,s,goal = self.learned()
        result = s.navigate_known(h.world,goal)
        self.assertEqual(result['status'],'ARRIVAL_VERIFIED_SIMULATED')
        self.assertEqual(len(result['attempts']),2)
        self.assertEqual(h.budget.snapshot()['spent']['model_requests'],0)
        self.assertEqual(len(h.world.dispatches),2)

    def test_known_route_failure_invalidates_old_edge_preserving_history(self):
        h,s,goal = self.learned(); h.world.no_effect=True
        result=s.navigate_known(h.world,goal)
        self.assertEqual(result['status'],'KNOWN_ROUTE_FAILED')
        self.assertEqual(len(h.world.dispatches),1)
        self.assertTrue(any(e['status']=='INVALIDATED' for e in s.graph.snapshot()['edges']))

    def test_dead_end_does_not_manufacture_connection_or_invoke_model(self):
        h=Harness(); s=session(h); goal=h.target(h.observe('info')); h.world.page='home'
        result=s.navigate_known(h.world,goal)
        self.assertEqual(result['status'],'NO_KNOWN_PATH')
        self.assertFalse(h.world.dispatches)

    def test_cancel_from_another_thread_during_callback_is_immediate_not_lock_blocked(self):
        h=Harness(); s=session(h); done=threading.Event()
        def callback():
            t=threading.Thread(target=lambda:(s.cancel(),done.set()),daemon=True)
            t.start()
            self.assertTrue(done.wait(0.5),'Cancellation held behind the session lock')
        h.world.after_dispatch=callback
        result=s.navigate_one(h.world)
        self.assertEqual(result['status'],'CANCELLED')
        self.assertEqual(len(h.world.dispatches),1)

    def test_clock_backwards_prevents_input(self):
        h=Harness(); s=session(h); h.clock.now=999
        result=s.navigate_one(h.world)
        self.assertEqual(result['status'],'CLOCK_ERROR')
        self.assertFalse(h.world.dispatches)

    def test_shared_elapsed_deadline_counts_model_error_and_wait(self):
        h=Harness(); s=session(h)
        def slow(o,c):
            h.clock.advance(10000)
            return {'observation_id':o['observation_id'],'candidate_id':c[0]['candidate_id']}
        result=s.navigate_one(h.world,proposal=FakeChooser(slow))
        self.assertEqual(result['status'],'TIMEOUT')
        self.assertFalse(h.world.dispatches)
        self.assertEqual(h.budget.snapshot()['spent']['model_requests'],1)

    def test_policy_mutation_cannot_reauthorize_node(self):
        h=Harness(); s=session(h); s.policy._rules[0]['selector']['resource_id']='other'
        result=s.navigate_one(h.world)
        self.assertEqual(result['status'],'SAFETY_POLICY_CHANGED')
        self.assertFalse(h.world.dispatches)

    def test_receipt_nonce_mismatch_keeps_dispatch_unknown(self):
        h=Harness(); s=session(h); original=h.world.dispatch
        def bad(c,n,d):
            r=original(c,n,d);r['dispatch_id']='wrong.dispatch';return r
        h.world.dispatch=bad
        result=s.navigate_one(h.world)
        self.assertNotEqual(result['status'],'ARRIVAL_VERIFIED_SIMULATED')
        self.assertEqual(s.bundle()['interactions'][0]['dispatch']['status'],'UNKNOWN')

    def test_malformed_receipt_cannot_escape_without_recorded_unknown_attempt(self):
        h=Harness(); s=session(h); original=h.world.dispatch
        def bad(c,n,d):
            original(c,n,d);return {'dispatch_id':n,'status':'SENT_SIMULATED'}
        h.world.dispatch=bad
        result=s.navigate_one(h.world)
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(len(s.bundle()['interactions']),1)

    def test_wrong_entity_after_input_does_not_verify(self):
        h=Harness(); goal=h.target(h.observe('details'));h.world.page='home';s=session(h)
        h.world.after_dispatch=lambda:setattr(h.world,'entity','Room 102')
        result=s.navigate_one(h.world,target=goal)
        self.assertEqual(result['status'],'UNCONFIRMED')
        self.assertEqual(s.graph.snapshot()['verified_simulated_edges'],0)

    def test_post_observe_exception_does_not_lose_dispatched_action(self):
        h=Harness();s=session(h)
        def fail(**kwargs):raise RuntimeError('transport details must not leak')
        h.world.after_dispatch=lambda:setattr(h.world,'observe',fail)
        result=s.navigate_one(h.world)
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(len(s.bundle()['interactions']),1)
        self.assertIsNone(s.bundle()['interactions'][0]['after'])

    def test_navigation_dynamic_business_change_conflicts_with_zero_journal(self):
        h=Harness()
        raw=h.world._nodes
        def nodes():
            return raw()+[node('slider','root',role='slider',resource_id='fixture:id/value',
                     range={'kind':'int','min':0,'max':100,'value':h.world.value})]
        h.world._nodes=nodes
        a=h.observe('home');h.world.value=80;b=h.observe('details')
        result=make_interaction('AGENT_NAVIGATION',a,b,action(),receipt(a,b),write_audit(),
                                entity_types=['room'],expected_target=h.target(b))
        self.assertNotEqual(result['status'],'ARRIVAL_VERIFIED_SIMULATED')
        self.assertIn('BUSINESS_STATE_CHANGED_WITHOUT_AUDIT',result['unknowns'])

    def test_observation_context_boot_change_stops_without_old_node_dispatch(self):
        h=Harness();s=session(h)
        original=h.world.guard
        def guard():
            r=original();r['boot_session_id']='other.boot';return r
        h.world.guard=guard
        # First observation establishes this boot; change it during model selection.
        def choose(o,c):
            h.world.guard=lambda:dict(original(),boot_session_id='third.boot')
            return {'observation_id':o['observation_id'],'candidate_id':c[0]['candidate_id']}
        result=s.navigate_one(h.world,proposal=FakeChooser(choose))
        self.assertEqual(result['status'],'OBSERVATION_SESSION_CHANGED')
        self.assertFalse(h.world.dispatches)

    def test_persistent_callback_cannot_reset_model_budget(self):
        scope=scope_fixture();scope['budgets']['max_model_requests']=1
        h=Harness(scope);s=session(h);bad=FakeChooser(lambda o,c:{'bad':True})
        self.assertEqual(s.navigate_one(h.world,proposal=bad)['status'],'REJECTED')
        self.assertEqual(s.navigate_one(h.world,proposal=bad)['status'],'BUDGET_EXCEEDED')
        self.assertEqual(bad.calls,1)

    def test_scroll_and_back_are_charged_as_actions_not_free_replanning(self):
        from safe_navigation import SafetyPolicy
        h=Harness();h.world.page='info';s=session(h)
        s.navigate_one(h.world)
        self.assertEqual(h.world.dispatches[0]['kind'],'BACK')
        self.assertEqual(h.budget.snapshot()['spent']['actions'],1)
        # Same policy digest is frozen; start a distinct allowed fixture session for scroll.
        h=Harness()
        raw=h.world._nodes
        h.world._nodes=lambda:[dict(n,resource_id='fixture:id/scroll') if n['node_local_id']=='root' else n for n in raw()]
        policy=SafetyPolicy([{'rule_id':'scroll','kind':'SCROLL','selector':{'resource_id':'fixture:id/scroll','role':'container'},
                             'effect':'NO_BUSINESS_WRITE','handler_evidence':'fixture:handler/scroll','review_cost_ms':0}])
        s=session(h,policy=policy);s.navigate_one(h.world)
        self.assertEqual(h.world.dispatches[0]['kind'],'SCROLL')
        self.assertEqual(h.budget.snapshot()['spent']['actions'],1)
