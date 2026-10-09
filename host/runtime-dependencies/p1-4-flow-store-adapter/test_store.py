import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from p14deps import fixture_bundle, canonical, environment
from flow_store import FlowStore, StoreError


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p14-store-')
        self.root = Path(self.temp.name)
        self.store = FlowStore.create(self.root)
        self.flow, self.package, self.task = fixture_bundle()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def draft(self, expected=0):
        return self.store.save_draft(canonical(self.flow), self.package, expected)

    def rejection(self, code, action):
        with self.assertRaises(StoreError) as caught:
            action()
        self.assertEqual(caught.exception.code, code)

    def test_S01_raw_draft_reload_no_rights(self):
        raw = json.dumps(self.flow, indent=3, ensure_ascii=False) + '\n'
        row = self.store.save_draft(raw, self.package, 0)
        self.store.close()
        self.store = FlowStore.open(self.root)
        loaded = self.store.load(row['key'])
        self.assertEqual(loaded['flow_raw'], raw)
        self.assertEqual(loaded['state'], 'DRAFT')
        self.assertFalse(loaded['execution_authority'])
        self.assertEqual(loaded['scopes'], [])
        self.assertNotIn('Task', canonical(loaded))
        self.assertEqual(loaded['dependencies']['registry_sha256'], self.flow['dependencies']['registry_sha256'])

    def test_S02_same_version_cannot_overwrite(self):
        row = self.draft()
        self.flow['purpose'] = 'different draft'
        self.rejection('VERSION_ALREADY_EXISTS', lambda: self.draft(1))
        self.assertNotEqual(self.store.load(row['key'])['flow']['purpose'], self.flow['purpose'])

    def test_S03_new_version_requires_current_head_and_diff(self):
        one = self.draft()
        self.flow['version'] = '1.0.1'
        self.package['flow_refs'][0]['version'] = '1.0.1'
        self.flow['purpose'] = 'TEST_FIXTURE second revision'
        self.rejection('REVISION_CONFLICT', lambda: self.draft(0))
        two = self.draft(1)
        self.assertEqual(two['parent_key'], one['key'])
        self.assertIn('/flow/purpose', two['diff'])
        self.assertEqual(self.store.load(one['key'])['state'], 'DRAFT')

    def test_S04_check_uses_actual_p13_and_does_not_save_task(self):
        row = self.draft()
        result = self.store.check(row['key'], 1, self.task, environment.audited_room_profile())
        self.assertEqual(result['state'], 'CHECKED')
        self.assertEqual(result['revision'], 2)
        self.assertEqual(result['scopes'], [])
        self.assertFalse(result['execution_authority'])
        text = canonical(result)
        self.assertNotIn(self.task['authorization_ref'], text)
        self.assertNotIn(self.task['cancellation_token_ref'], text)

    def test_S05_bad_version_and_bad_reference_no_partial_insert(self):
        for mutator in (lambda: self.flow.update(schema_version='99'),
                        lambda: self.package['flow_refs'][0].update(id='flow.missing')):
            self.flow, self.package, self.task = fixture_bundle()
            mutator()
            with self.assertRaises(StoreError):
                self.draft()
        self.assertEqual(self.store.list_versions(), [])

    def test_S06_schema_corruption_does_not_clear_history(self):
        self.draft()
        self.store.close()
        with closing(sqlite3.connect(self.root / FlowStore.FILENAME)) as db, db:
            db.execute("UPDATE metadata SET value='99' WHERE name='schema'")
        self.rejection('STORE_SCHEMA_UNSUPPORTED', lambda: FlowStore.open(self.root))
        with closing(sqlite3.connect(self.root / FlowStore.FILENAME)) as db, db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM versions').fetchone()[0], 1)

    def test_S07_corrupt_body_is_explicit(self):
        row = self.draft()
        with closing(sqlite3.connect(self.root / FlowStore.FILENAME)) as db, db:
            db.execute("UPDATE versions SET body_json='{}' WHERE key=?", (row['key'],))
        self.rejection('STORE_DIGEST_ERROR', lambda: self.store.load(row['key']))

    def test_S08_missing_file_is_not_recreated(self):
        missing = self.root / 'missing'
        self.rejection('STORE_NOT_FOUND', lambda: FlowStore.open(missing))
        self.assertFalse(missing.exists())

    def test_L01_model_claims_do_not_create_validated_or_published(self):
        self.flow['published'] = True
        with self.assertRaises(StoreError):
            self.draft()
        self.flow.pop('published')
        self.flow['verified_scope'] = [{'model_claim': 'SUCCESS'}]
        with self.assertRaises(StoreError):
            self.draft()
        self.assertEqual(self.store.list_versions(), [])

    def test_L02_conflicting_revision_and_irreversible_invalidation(self):
        row = self.draft()
        changed = self.store.invalidate(row['key'], 1, 'INVALIDATED', 'operator.source_changed')
        self.assertEqual(changed['state'], 'INVALIDATED')
        self.rejection('REVISION_CONFLICT', lambda: self.store.invalidate(row['key'], 1, 'REVOKED', 'operator.cancel'))
        self.rejection('STATE_TRANSITION_ERROR', lambda: self.store.check(row['key'], 2, self.task, None))

    def test_S09_arbitrary_refs_are_not_dereferenced(self):
        self.package['evidence'][0]['ref'] = 'https://example.invalid/never-followed'
        self.assertEqual(self.draft()['state'], 'DRAFT')
        self.assertFalse(self.store.load(self.flow['id'] + '@' + self.flow['version'])['execution_authority'])


if __name__ == '__main__':
    unittest.main()
