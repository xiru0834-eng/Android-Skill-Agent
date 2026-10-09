"""Persistence contract tests: local SQLite data, not a live execution checkpoint."""
import copy
from pathlib import Path
import sqlite3
import tempfile
import unittest
from trace_store import TraceStore, validate_bundle
from trace_contract import TraceError
from test_support import Harness
from test_session import session

def bundle_fixture():
    h=Harness();s=session(h);goal=h.target(h.observe('details'));h.world.page='home'
    s.navigate_one(h.world,target=goal)
    return s.bundle()

class StoreTests(unittest.TestCase):
    def test_read_only_open_and_missing_read_do_not_write_or_create(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trace.sqlite';b=bundle_fixture()
            with TraceStore(p) as db:db.append(b,expected_revision=0)
            before=p.read_bytes()
            with TraceStore(p,read_only=True) as db:
                self.assertEqual(db.read(b['trace_id'])['status'],'FOUND')
                with self.assertRaises(TraceError):db.append(bundle_fixture(),expected_revision=1)
            self.assertEqual(before,p.read_bytes())
            missing=Path(tmp)/'missing.sqlite'
            with self.assertRaises(TraceError):TraceStore(missing,read_only=True)
            self.assertFalse(missing.exists())
    def test_append_read_close_and_reopen_preserves_ids_no_authority(self):
        bundle=bundle_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'trace.sqlite'
            with TraceStore(path) as db:
                receipt=db.append(bundle,expected_revision=0)
                self.assertEqual(receipt['revision'],1)
                self.assertEqual(db.read(bundle['trace_id'])['bundle'],bundle)
            with TraceStore(path) as db:
                loaded=db.read(bundle['trace_id'])
                self.assertFalse(loaded['execution_authority'])
                self.assertEqual(loaded['restore_mode'],'EVIDENCE_ONLY_NO_SESSION_RESUME')
                self.assertEqual(loaded['bundle']['map']['real_verified_edges'],0)

    def test_modified_interaction_status_or_source_counts_rejected(self):
        b=bundle_fixture()
        for mutate in (lambda x:x['interactions'][0].update(status='SUCCESS'),
                       lambda x:x['source_counts'].update(HUMAN_DEMONSTRATION=10),
                       lambda x:x['map'].update(real_verified_edges=1)):
            x=copy.deepcopy(b);mutate(x)
            with self.subTest(x=x),self.assertRaises(TraceError):validate_bundle(x)

    def test_fabricated_map_edge_cannot_be_saved_as_verified(self):
        b=bundle_fixture();b['map']['edges'][0]['evidence']['interaction_id']='fake'
        with self.assertRaises(TraceError):validate_bundle(b)

    def test_old_observation_id_or_hash_mismatch_rejected(self):
        b=bundle_fixture();b['interactions'][0]['before']['sha256']='f'*64
        with self.assertRaises(TraceError):validate_bundle(b)

    def test_duplicate_dispatch_or_observation_rejected(self):
        for field in ('interactions','observations'):
            b=bundle_fixture();b[field].append(copy.deepcopy(b[field][0]))
            with self.subTest(field=field),self.assertRaises(TraceError):validate_bundle(b)

    def test_nested_authority_and_live_objects_never_serialized(self):
        for obj in (lambda x:x['diagnostics'].append({'execution_authority':True}),
                    lambda x:x.update(diagnostics=[object()])):
            b=bundle_fixture();obj(b)
            with self.assertRaises(TraceError):validate_bundle(b)

    def test_compare_and_swap_and_duplicate_trace_leave_prior_data(self):
        b=bundle_fixture()
        with tempfile.TemporaryDirectory() as tmp, TraceStore(Path(tmp)/'trace.sqlite') as db:
            db.append(b,expected_revision=0)
            with self.assertRaises(TraceError):db.append(bundle_fixture(),expected_revision=0)
            with self.assertRaises(TraceError):db.append(b,expected_revision=1)
            self.assertEqual(db.revision(),1)
            self.assertEqual(len(db.list_traces()['items']),1)

    def test_failure_before_commit_rolls_back_metadata_and_row(self):
        with tempfile.TemporaryDirectory() as tmp, TraceStore(Path(tmp)/'trace.sqlite') as db:
            with self.assertRaises(TraceError):db.append(bundle_fixture(),expected_revision=0,fail_before_commit=True)
            self.assertEqual(db.revision(),0)
            self.assertEqual(db.list_traces()['items'],[])

    def test_digest_corruption_returns_error_not_empty_history(self):
        b=bundle_fixture()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trace.sqlite'
            with TraceStore(p) as db:db.append(b,expected_revision=0)
            con=sqlite3.connect(p);con.execute("UPDATE traces SET payload='{}'");con.commit();con.close()
            with TraceStore(p) as db:
                with self.assertRaises(TraceError):db.read(b['trace_id'])

    def test_existing_foreign_database_is_not_changed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'foreign.sqlite'
            con=sqlite3.connect(p);con.execute('CREATE TABLE user_data(value)');con.commit();con.close()
            before=p.read_bytes()
            with self.assertRaises(TraceError):TraceStore(p)
            self.assertEqual(before,p.read_bytes())

    def test_bad_schema_version_is_not_migrated_or_cleared(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'trace.sqlite'
            with TraceStore(p):pass
            con=sqlite3.connect(p);con.execute("UPDATE metadata SET version='future'");con.commit();con.close()
            before=p.read_bytes()
            with self.assertRaises(TraceError):TraceStore(p)
            self.assertEqual(before,p.read_bytes())

    def test_read_does_not_observe_model_or_dispatch(self):
        h=Harness();s=session(h);s.navigate_one(h.world);b=s.bundle()
        counts=(h.world.tree_reads,len(h.world.dispatches),h.budget.snapshot()['spent']['model_requests'])
        with tempfile.TemporaryDirectory() as tmp, TraceStore(Path(tmp)/'trace.sqlite') as db:
            db.append(b,expected_revision=0);db.read(b['trace_id']);db.list_traces()
        self.assertEqual(counts,(h.world.tree_reads,len(h.world.dispatches),h.budget.snapshot()['spent']['model_requests']))

    def test_invalid_path_id_limit_or_revision_rejected(self):
        with tempfile.TemporaryDirectory() as tmp, TraceStore(Path(tmp)/'trace.sqlite') as db:
            for value in ('../file','C:/other',None):
                with self.assertRaises(TraceError):db.read(value)
            for limit in (-1,0,101,True,'20'):
                with self.assertRaises(TraceError):db.list_traces(limit=limit)
            for rev in (-1,True,'0'):
                with self.assertRaises(TraceError):db.append(bundle_fixture(),expected_revision=rev)
