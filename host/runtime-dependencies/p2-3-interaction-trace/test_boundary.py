"""Final offline boundary review. No production, native, or paid calls."""
import copy
import tempfile
from pathlib import Path
import unittest
from p23deps import derive_page
from test_support import Harness, scope_fixture, action, receipt, write_audit
from test_session import session
from test_store import bundle_fixture
from trace_contract import TraceError
from trace_store import TraceStore, validate_bundle

class BoundaryTests(unittest.TestCase):
    def test_cancelled_bundle_can_reload_but_cannot_resume_session(self):
        h=Harness();s=session(h);h.world.after_dispatch=s.cancel;s.navigate_one(h.world)
        with tempfile.TemporaryDirectory() as tmp, TraceStore(Path(tmp)/'evidence.sqlite') as db:
            b=s.bundle();db.append(b,expected_revision=0)
            self.assertEqual(db.read(b['trace_id'])['bundle']['state'],'CANCELLED')
            self.assertEqual(db.read(b['trace_id'])['restore_mode'],'EVIDENCE_ONLY_NO_SESSION_RESUME')

    def test_hypothesis_can_be_stored_but_never_searches(self):
        h=Harness();s=session(h);s.navigate_one(h.world)
        a=h.observe('home');b=h.observe('info')
        s._put_observation(a);s._put_observation(b)
        s.graph.add_hypothesis(derive_page(a,entity_types=['room']),h.target(b),'fixture:model')
        stored=validate_bundle(s.bundle())
        self.assertTrue(any(e['status']=='HYPOTHESIS' for e in stored['map']['edges']))
        self.assertEqual(s.graph.search(derive_page(a,entity_types=['room']),h.target(b))['status'],'NO_KNOWN_PATH')

    def test_invalidated_graph_can_roundtrip_without_restoring_trust(self):
        h=Harness();s=session(h);goal=h.target(h.observe('details'));h.world.page='home';s.navigate_one(h.world,target=goal)
        eid=s.graph.snapshot()['edges'][0]['edge_id'];s.graph.invalidate(eid,'fixture:arrival-failed')
        b=validate_bundle(s.bundle())
        self.assertEqual(b['map']['edges'][0]['status'],'INVALIDATED')

    def test_observation_budget_exhaustion_records_dispatch_even_without_post(self):
        scope=scope_fixture();scope['budgets']['max_observations']=2
        h=Harness(scope);s=session(h);result=s.navigate_one(h.world)
        self.assertEqual(len(h.world.dispatches),1)
        self.assertIsNone(s.bundle()['interactions'][0]['after'])
        self.assertNotEqual(result['status'],'ARRIVAL_VERIFIED_SIMULATED')

    def test_time_limited_post_wait_does_not_reset_deadline(self):
        scope=scope_fixture();scope['budgets']['max_time_ms']=200
        h=Harness(scope);goal=h.target(h.observe('details'));h.world.page='home';h.world.no_effect=True;s=session(h)
        result=s.navigate_one(h.world,target=goal)
        self.assertEqual(result['status'],'TIMEOUT')
        self.assertEqual(h.budget.snapshot()['deadline_ms'],1200)
        self.assertEqual(len(h.world.dispatches),1)

    def test_wrong_window_or_root_error_never_dispatches(self):
        for failure in ('window','root'):
            h=Harness();s=session(h)
            if failure=='window':
                original=h.world.guard
                h.world.guard=lambda:dict(original(),host_device_id='other.host')
            else:
                original=h.world.read_frame
                def frame(d,a):
                    r=original(d,a);r['tree']['root_readable']=False;r['tree']['nodes']=[];return r
                h.world.read_frame=frame
            result=s.navigate_one(h.world)
            self.assertNotEqual(result['status'],'ARRIVAL_VERIFIED_SIMULATED')
            self.assertFalse(h.world.dispatches)

    def test_storage_budget_exhaustion_does_not_dispatch(self):
        scope=scope_fixture();scope['budgets']['max_storage_bytes']=1
        h=Harness(scope);s=session(h)
        self.assertEqual(s.navigate_one(h.world)['status'],'BUDGET_EXCEEDED')
        self.assertFalse(h.world.dispatches)

    def test_current_safe_unrelated_navigation_can_be_recorded_then_observed_back(self):
        h=Harness();s=session(h);h.world.page='unrelated';goal=h.target(h.observe('home'));h.world.page='unrelated'
        result=s.navigate_one(h.world,target=goal)
        self.assertEqual(result['status'],'ARRIVAL_VERIFIED_SIMULATED')
        self.assertEqual(len(s.graph.snapshot()['edges']),1)
        self.assertEqual(s.graph.snapshot()['edges'][0]['action']['kind'],'BACK')

    def test_page_outside_scope_or_unconfirmed_entity_refuses(self):
        for value in ('scope','entity'):
            h=Harness();s=session(h)
            if value=='scope':
                s.scope['allowed_pages']=['home']
            else:h.world.entity='something.untyped'
            result=s.navigate_one(h.world)
            self.assertIn(result['status'],('SCOPE_CHANGED','IDENTITY_UNCONFIRMED'))
            self.assertFalse(h.world.dispatches)

    def test_fabricated_attempt_arrival_or_missing_reference_rejected(self):
        b=bundle_fixture()
        for mutate in (lambda x:x['navigation_attempts'][0].update(interaction_id=None),
                       lambda x:x['navigation_attempts'][0].update(before_observation_id='fake')):
            x=copy.deepcopy(b);mutate(x)
            with self.assertRaises(TraceError):validate_bundle(x)

    def test_mutated_observation_local_node_does_not_wash_evidence(self):
        b=bundle_fixture();b['observations'][0]['tree']['nodes'][-1]['text']='Other'
        with self.assertRaises(TraceError):validate_bundle(b)

    def test_bad_target_json_types_fail_as_contract_errors(self):
        h=Harness();s=session(h)
        for val in ([],True,{'page_instance_id':[],'entity_keys':None,'navigation_context':None}):
            with self.assertRaises(TraceError):s.navigate_one(h.world,target=val)
        self.assertFalse(h.world.dispatches)
