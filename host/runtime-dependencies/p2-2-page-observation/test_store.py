"""Real local SQLite transactions/reload; never Android observation evidence."""
import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from observation_store import ObservationStore
from observation_tree import ObservationError
from test_identity import observation
from p22deps import LearningBudget, ScopeError
from test_support import Clock, scope_fixture


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p22-store-')
        self.path = Path(self.temp.name) / 'memory.sqlite'
        self.store = ObservationStore(self.path, create=True)
        self.budget = LearningBudget(scope_fixture(), clock=Clock())

    def tearDown(self):
        self.store.close(); self.temp.cleanup()

    def add(self, obs=None, **kwargs):
        return self.store.append(obs or observation(), entity_types=['room'], budget=self.budget, **kwargs)

    def test_append_read_reload_preserve_original_id_times_evidence_and_no_authority(self):
        obs = observation(); self.add(obs)
        self.store.close(); self.store = ObservationStore(self.path)
        record = self.store.inspect_observation(obs['observation_id'])
        self.assertEqual(record['status'], 'FOUND'); self.assertEqual(record['observation'], obs)
        self.assertEqual(record['memory_revision'], 1); self.assertFalse(record['execution_authority'])
        self.assertEqual(self.store.search_in_observation(obs['observation_id'], role='slider')['candidate_count'], 1)

    def test_failed_observation_is_diagnostic_not_latest_valid(self):
        obs = observation(); self.add(obs)
        failed = copy.deepcopy(obs); failed['observation_id'] = 'failed-observation'
        failed.update(capture_status='ROOT_UNAVAILABLE', tree=None, screenshot=None, consistency=None)
        self.add(failed)
        latest = self.store.latest_reference(obs['environment'], host_device_id=obs['host_device_id'],
            boot_session_id=obs['boot_session_id'], now_elapsed_ms=1040)
        self.assertEqual(latest['observation']['observation_id'], obs['observation_id'])
        self.assertEqual(self.store.inspect_observation('failed-observation')['page']['identity_status'], 'UNAVAILABLE')

    def test_environment_host_boot_and_age_are_explicit_not_current_ui_fact(self):
        obs = observation(); self.add(obs)
        kwargs = dict(host_device_id=obs['host_device_id'], boot_session_id=obs['boot_session_id'], now_elapsed_ms=1040)
        fresh = self.store.latest_reference(obs['environment'], **kwargs)
        self.assertEqual(fresh['status'], 'RECENT_MEMORY_REFERENCE'); self.assertFalse(fresh['current_ui_confirmed'])
        other_env = dict(obs['environment'], ui_revision='u1')
        self.assertEqual(self.store.latest_reference(other_env, **kwargs)['status'], 'NOT_FOUND')
        self.assertEqual(self.store.latest_reference(obs['environment'], **dict(kwargs, host_device_id='other'))['status'], 'NOT_FOUND')
        self.assertEqual(self.store.latest_reference(obs['environment'], **dict(kwargs, boot_session_id='new-boot'))['status'], 'HISTORICAL_SESSION')
        self.assertEqual(self.store.latest_reference(obs['environment'], **dict(kwargs, now_elapsed_ms=5000))['status'], 'EXPIRED_REFERENCE')
        self.assertEqual(self.store.latest_reference(obs['environment'], **dict(kwargs, now_elapsed_ms=0))['status'], 'CLOCK_UNCONFIRMED')

    def test_duplicate_observation_and_revision_conflict_do_not_overwrite(self):
        obs = observation(); self.add(obs)
        with self.assertRaisesRegex(ObservationError, 'DUPLICATE_OBSERVATION'): self.add(obs)
        with self.assertRaisesRegex(ObservationError, 'REVISION_CONFLICT'): self.add(expected_revision=0)
        self.assertEqual(self.store.revision(), 1)

    def test_actual_transaction_failure_does_not_publish_half_record(self):
        self.store.db.execute("CREATE TRIGGER abort_commit BEFORE UPDATE ON meta BEGIN SELECT RAISE(ABORT, 'fault'); END")
        with self.assertRaisesRegex(ObservationError, 'STORAGE_ERROR'): self.add()
        self.assertEqual(self.store.revision(), 0)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM records').fetchone()[0], 0)

    def test_digest_corruption_reported_not_silent_reset(self):
        obs = observation(); self.add(obs)
        self.store.db.execute("UPDATE records SET payload='{}' WHERE observation_id=?", (obs['observation_id'],))
        with self.assertRaisesRegex(ObservationError, 'MEMORY_CORRUPT'): self.store.inspect_observation(obs['observation_id'])
        self.assertEqual(self.store.revision(), 1)

    def test_schema_incompatibility_does_not_replace_existing_database(self):
        self.store.db.execute('UPDATE meta SET schema_version=99'); self.store.close()
        with self.assertRaisesRegex(ObservationError, 'SCHEMA_INCOMPATIBLE'): ObservationStore(self.path)
        db = sqlite3.connect(self.path)
        try: self.assertEqual(db.execute('SELECT schema_version FROM meta').fetchone()[0], 99)
        finally: db.close()

    def test_missing_database_and_bad_index_are_explicit_without_creation(self):
        missing = Path(self.temp.name) / 'missing.sqlite'
        with self.assertRaisesRegex(ObservationError, 'MEMORY_NOT_FOUND'): ObservationStore(missing)
        self.assertFalse(missing.exists())
        self.store.db.execute('DROP TABLE records'); self.store.close()
        with self.assertRaisesRegex(ObservationError, 'MEMORY_CORRUPT'): ObservationStore(self.path)

    def test_storage_payload_quota_and_scope_budget_block_without_writes(self):
        self.store.max_payload_bytes = 1
        with self.assertRaisesRegex(ObservationError, 'STORAGE_CAPACITY'): self.add()
        self.assertEqual(self.store.revision(), 0)
        self.store.max_payload_bytes = 1000000
        scope = scope_fixture(); scope['budgets']['max_storage_bytes'] = 1
        # Changed scope hash is refused before any persistence.
        wrong = LearningBudget(scope, clock=Clock())
        with self.assertRaises((ObservationError, ScopeError)):
            self.store.append(observation(), entity_types=['room'], budget=wrong)
        self.assertEqual(self.store.revision(), 0)

    def test_read_only_api_has_no_capture_port_and_rejects_path_as_id(self):
        obs = observation(); self.add(obs)
        self.assertFalse(hasattr(self.store, 'port'))
        self.assertEqual(self.store.inspect_observation('missing')['status'], 'NOT_FOUND')
        with self.assertRaisesRegex(ObservationError, 'INVALID_QUERY'): self.store.inspect_observation('../memory.sqlite')
        with self.assertRaisesRegex(ObservationError, 'INVALID_LIMIT'): self.store.search_in_observation(obs['observation_id'], limit=-1)
        with self.assertRaisesRegex(ObservationError, 'INVALID_QUERY'):
            self.store.latest_reference(obs['environment'], host_device_id=obs['host_device_id'], boot_session_id=obs['boot_session_id'], now_elapsed_ms=-1)

    def test_live_object_or_fake_channel_does_not_enter_store(self):
        for field, value in [('node_handle', object()), ('channel', 'REAL_ANDROID')]:
            obs = observation(); obs[field] = value
            with self.subTest(field=field), self.assertRaises(ObservationError): self.add(obs)
        self.assertEqual(self.store.revision(), 0)

    def test_simultaneous_writer_revision_is_seen_after_reload(self):
        other = ObservationStore(self.path)
        try:
            self.add(expected_revision=0)
            with self.assertRaisesRegex(ObservationError, 'REVISION_CONFLICT'):
                other.append(observation(), entity_types=['room'], budget=self.budget, expected_revision=0)
            self.assertEqual(other.revision(), 1)
        finally: other.close()

    def test_metadata_index_contradiction_is_not_another_environment_fact(self):
        obs = observation(); self.add(obs)
        self.store.db.execute('UPDATE records SET host=? WHERE observation_id=?',('other-host',obs['observation_id']))
        with self.assertRaisesRegex(ObservationError,'MEMORY_CORRUPT'): self.store.inspect_observation(obs['observation_id'])


if __name__ == '__main__': unittest.main()
