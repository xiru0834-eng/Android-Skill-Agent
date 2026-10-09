import copy
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from bundle_contract import BundleError
from bundle_store import BundleStore
from test_support import bundle_fixture,ENV


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'material.sqlite'
    def tearDown(self):self.temp.cleanup()
    def test_real_file_reload(self):
        b=bundle_fixture()
        with BundleStore(self.path,create=True) as s:s.append(b,expected_revision=0)
        with BundleStore(self.path,read_only=True) as s:
            self.assertEqual(s.snapshot(ENV)['bundles'][0]['bundle'],b)
    def test_missing_read_only_store_never_created(self):
        with self.assertRaisesRegex(BundleError,'STORE_NOT_FOUND'):BundleStore(self.path,read_only=True)
        self.assertFalse(self.path.exists())
    def test_partial_transaction_rolls_back(self):
        with BundleStore(self.path,create=True) as s:
            with self.assertRaisesRegex(BundleError,'STORAGE_INTERRUPTION'):s.append(bundle_fixture(),expected_revision=0,fail_before_commit=True)
            self.assertEqual(s.snapshot(ENV)['bundles'],[]);self.assertEqual(s.revision(),0)
    def test_capacity_failure_keeps_existing_material(self):
        with BundleStore(self.path,create=True,max_payload_bytes=10000) as s:
            s.append(bundle_fixture(),expected_revision=0);s.max_payload_bytes=1
            with self.assertRaisesRegex(BundleError,'STORAGE_CAPACITY'):s.append(bundle_fixture(),expected_revision=1)
            s.max_payload_bytes=10000;self.assertEqual(len(s.snapshot(ENV)['bundles']),1)
    def test_compare_and_swap_across_two_connections(self):
        with BundleStore(self.path,create=True) as a,BundleStore(self.path) as b:
            a.append(bundle_fixture(),expected_revision=0)
            with self.assertRaisesRegex(BundleError,'REVISION_CONFLICT'):b.append(bundle_fixture(),expected_revision=0)
            self.assertEqual(b.revision(),1)
    def test_read_only_connection_cannot_append(self):
        with BundleStore(self.path,create=True):pass
        with BundleStore(self.path,read_only=True) as s:
            with self.assertRaisesRegex(BundleError,'STORE_READ_ONLY'):s.append(bundle_fixture(),expected_revision=0)
    def test_corrupt_digest_not_silently_cleared(self):
        with BundleStore(self.path,create=True) as s:s.append(bundle_fixture(),expected_revision=0)
        with closing(sqlite3.connect(self.path)) as c, c:c.execute("UPDATE bundles SET payload_digest='bad'")
        with BundleStore(self.path,read_only=True) as s:
            with self.assertRaisesRegex(BundleError,'STORE_DIGEST_ERROR'):s.snapshot(ENV)
        self.assertTrue(self.path.exists())
    def test_revision_cursor_cannot_mix_new_data(self):
        with BundleStore(self.path,create=True) as s:
            s.append(bundle_fixture(),expected_revision=0)
            with self.assertRaisesRegex(BundleError,'REVISION_CONFLICT'):s.snapshot(ENV,expected_revision=0)
    def test_foreign_store_not_dropped(self):
        with closing(sqlite3.connect(self.path)) as c, c:c.execute('CREATE TABLE original(value TEXT)')
        with self.assertRaisesRegex(BundleError,'FOREIGN_STORE'):BundleStore(self.path)
        with closing(sqlite3.connect(self.path)) as c:self.assertEqual(c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchone()[0],'original')
    def test_duplicate_bundle_id_not_overwritten(self):
        b=bundle_fixture()
        with BundleStore(self.path,create=True) as s:
            s.append(b,expected_revision=0)
            with self.assertRaisesRegex(BundleError,'DUPLICATE_BUNDLE'):s.append(b,expected_revision=1)
    def test_app_build_and_ui_isolation(self):
        with BundleStore(self.path,create=True) as s:
            s.append(bundle_fixture(),expected_revision=0)
            for name in ('app_package','app_build','ui_revision'):
                env=dict(ENV);env[name]='different'
                self.assertEqual(s.snapshot(env)['bundles'],[])
    def test_missing_ref_rejected_before_write(self):
        b=bundle_fixture();b['pages'][0]['elements'][0]['source_ids']=['missing']
        with BundleStore(self.path,create=True) as s:
            with self.assertRaises(BundleError):s.append(b,expected_revision=0)
            self.assertEqual(s.revision(),0)

if __name__=='__main__':unittest.main()
