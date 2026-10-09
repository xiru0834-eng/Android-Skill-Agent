"""Review regressions: receipts, quotas and persistence integrity."""
import copy
from pathlib import Path
import tempfile
import unittest
from test_support import Harness, scope_fixture
from test_session import session
from test_store import bundle_fixture
from trace_store import TraceStore, validate_bundle
from trace_contract import TraceError

class ReviewTests(unittest.TestCase):
    def test_future_dispatch_time_cannot_drop_trace_or_verify(self):
        h=Harness();s=session(h);original=h.world.dispatch
        def bad(c,n,d):
            r=original(c,n,d);r['finished_elapsed_ms']+=10000;return r
        h.world.dispatch=bad
        result=s.navigate_one(h.world)
        self.assertEqual(result['status'],'FAILED')
        self.assertEqual(len(s.bundle()['interactions']),1)

    def test_malformed_journal_is_unknown_not_lost_dispatched_action(self):
        h=Harness();s=session(h);h.world.write_audit=lambda:{'coverage':'COMPLETE'}
        result=s.navigate_one(h.world)
        self.assertEqual(result['status'],'UNCONFIRMED')
        self.assertEqual(len(s.bundle()['interactions']),1)
        self.assertIn('BUSINESS_EFFECT_UNKNOWN',s.bundle()['interactions'][0]['unknowns'])

    def test_trace_bytes_including_graph_and_attempts_use_same_storage_budget(self):
        h=Harness();s=session(h);s.navigate_one(h.world)
        from p23deps import canonical
        b=s.bundle()
        payload={k:b[k] for k in ('observations','interactions','map','navigation_attempts','diagnostics')}
        actual=len(canonical(payload).encode('utf-8'))
        self.assertGreaterEqual(h.budget.snapshot()['spent']['storage_bytes']+b.get('forensic_tail_bytes',0),actual)

    def test_oversized_existing_store_and_trace_storage_cap_reject_new_writes(self):
        b=bundle_fixture()
        with tempfile.TemporaryDirectory() as tmp,TraceStore(Path(tmp)/'trace.sqlite',max_bytes=100) as db:
            with self.assertRaises(TraceError):db.append(b,expected_revision=0)
            self.assertEqual(db.revision(),0)

    def test_two_connections_cas_and_read_snapshot_remain_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trace.sqlite'
            with TraceStore(p) as a,TraceStore(p) as b:
                a.append(bundle_fixture(),expected_revision=0)
                self.assertEqual(b.revision(),1)
                with self.assertRaises(TraceError):b.append(bundle_fixture(),expected_revision=0)
                self.assertEqual(a.list_traces()['total'],1)

    def test_mutated_scope_host_or_budget_data_is_explicit_error(self):
        b=bundle_fixture()
        mutations=(lambda x:x.update(budget=None),
                   lambda x:x.update(scope=None),
                   lambda x:x['observations'][0].update(scope_hash='f'*64),
                   lambda x:x['budget'].pop('session_id'))
        for mutate in mutations:
            c=copy.deepcopy(b);mutate(c)
            with self.assertRaises(TraceError):validate_bundle(c)
