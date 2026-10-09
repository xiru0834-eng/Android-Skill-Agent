"""Transactional inert evidence memory; no device port, input permission or capture."""
import json
from pathlib import Path
import re
import sqlite3

from observation_capture import VALID
from observation_identity import derive_page, search_elements
from observation_tree import ObservationError, identifier, require
from observation_contract import validate_observation
from p22deps import LearningBudget, canonical, digest

SCHEMA_VERSION = 1
MAX_PAYLOAD_BYTES = 64 * 1024 * 1024  # Stored payload quota, not a filesystem free-space claim.

def _query_id(value):
    require(identifier(value) and re.fullmatch(r'[A-Za-z0-9_.:-]+', value) is not None, 'INVALID_QUERY')
    return value


class ObservationStore:
    def __init__(self, path, *, create=False, max_payload_bytes=MAX_PAYLOAD_BYTES):
        require(type(create) is bool and type(max_payload_bytes) is int and max_payload_bytes > 0, 'INVALID_STORE_CONFIG')
        self.path = Path(path).absolute(); self.max_payload_bytes = max_payload_bytes
        if not self.path.exists():
            require(create, 'MEMORY_NOT_FOUND')
            # Explicit local path authority is required at construction, never at query time.
            require(self.path.parent.is_dir(), 'MEMORY_NOT_FOUND')
            self.db = sqlite3.connect(self.path, isolation_level=None, timeout=0.2)
            try:
                self.db.executescript('''BEGIN IMMEDIATE;
                    CREATE TABLE meta(singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version INTEGER NOT NULL,
                                      revision INTEGER NOT NULL, payload_bytes INTEGER NOT NULL);
                    INSERT INTO meta VALUES(1,1,0,0);
                    CREATE TABLE records(observation_id TEXT PRIMARY KEY, env_key TEXT NOT NULL, host TEXT,
                                         boot TEXT, ended INTEGER NOT NULL, valid INTEGER NOT NULL,
                                         payload TEXT NOT NULL, payload_digest TEXT NOT NULL, revision INTEGER UNIQUE NOT NULL);
                    COMMIT;''')
            except sqlite3.Error as error:
                self.db.close(); raise ObservationError('STORAGE_ERROR') from error
        else:
            self.db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, isolation_level=None, timeout=0.2)
        try:
            self.db.execute('PRAGMA foreign_keys=ON')
            row = self.db.execute('SELECT schema_version, revision, payload_bytes FROM meta WHERE singleton=1').fetchone()
            require(row is not None and row[0] == SCHEMA_VERSION, 'SCHEMA_INCOMPATIBLE')
            require(type(row[1]) is int and row[1] >= 0 and row[2] >= 0, 'MEMORY_CORRUPT')
            self.db.execute('SELECT observation_id, env_key, host, boot, ended, valid, payload, payload_digest, revision FROM records LIMIT 0')
            require(self.db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'MEMORY_CORRUPT')
        except (sqlite3.Error, ObservationError) as error:
            self.db.close()
            if isinstance(error, ObservationError): raise
            raise ObservationError('MEMORY_CORRUPT') from error

    def close(self):
        self.db.close()

    def revision(self):
        try: return self.db.execute('SELECT revision FROM meta WHERE singleton=1').fetchone()[0]
        except (sqlite3.Error, TypeError) as error: raise ObservationError('MEMORY_CORRUPT') from error

    def append(self, value, *, entity_types, budget, expected_revision=None):
        obs = validate_observation(value)
        require(type(budget) is LearningBudget, 'SCOPE_BUDGET_REQUIRED')
        if expected_revision is not None:
            require(type(expected_revision) is int and expected_revision >= 0, 'REVISION_CONFLICT')
        snapshot = budget.snapshot()
        require(snapshot['scope_hash'] == obs['scope_hash'] and snapshot['environment_id'] == obs['environment']['environment_id'],
                'ENVIRONMENT_ERROR')
        page = derive_page(obs, entity_types=entity_types)
        payload = {'observation': obs, 'page': page}
        encoded = canonical(payload); size = len(encoded.encode('utf-8'))
        try:
            self.db.execute('BEGIN IMMEDIATE')
            revision, used = self.db.execute('SELECT revision, payload_bytes FROM meta WHERE singleton=1').fetchone()
            require(expected_revision is None or expected_revision == revision, 'REVISION_CONFLICT')
            require(self.db.execute('SELECT 1 FROM records WHERE observation_id=?', (obs['observation_id'],)).fetchone() is None,
                    'DUPLICATE_OBSERVATION')
            require(used + size <= self.max_payload_bytes, 'STORAGE_CAPACITY')
            budget.charge({'storage_bytes': size}, scope_hash=obs['scope_hash'], environment=obs['environment']['environment_id'])
            new_revision = revision + 1
            self.db.execute('INSERT INTO records VALUES(?,?,?,?,?,?,?,?,?)', (
                obs['observation_id'], digest(obs['environment']), obs['host_device_id'], obs['boot_session_id'],
                obs['ended_elapsed_ms'], int(obs['capture_status'] in VALID), encoded, digest(payload), new_revision))
            self.db.execute('UPDATE meta SET revision=?, payload_bytes=? WHERE singleton=1', (new_revision, used + size))
            self.db.execute('COMMIT')
            return {'status': 'SAVED', 'observation_id': obs['observation_id'], 'memory_revision': new_revision,
                    'payload_bytes': size, 'execution_authority': False}
        except Exception as error:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            if isinstance(error, sqlite3.Error): raise ObservationError('STORAGE_ERROR') from error
            raise

    def _record(self, row):
        if row is None:
            return {'status': 'NOT_FOUND', 'memory_revision': self.revision(), 'execution_authority': False}
        try:
            payload = json.loads(row['payload'])
            require(digest(payload) == row['payload_digest'], 'MEMORY_CORRUPT')
            obs = validate_observation(payload['observation'])
            require(row['observation_id'] == obs['observation_id'] and row['env_key'] == digest(obs['environment'])
                    and row['host'] == obs['host_device_id'] and row['boot'] == obs['boot_session_id']
                    and row['ended'] == obs['ended_elapsed_ms'] and row['valid'] == int(obs['capture_status'] in VALID)
                    and 0 < row['revision'] <= self.revision(), 'MEMORY_CORRUPT')
            require(payload['page']['observation_id'] == obs['observation_id']
                    and payload['page']['execution_authority'] is False, 'MEMORY_CORRUPT')
            return dict(payload, status='FOUND', record_revision=row['revision'], memory_revision=self.revision(),
                        current_ui_confirmed=False, execution_authority=False)
        except (ValueError, KeyError, TypeError) as error:
            raise ObservationError('MEMORY_CORRUPT') from error

    def _read(self, query, params):
        try:
            self.db.row_factory = sqlite3.Row
            return self._record(self.db.execute(query, params).fetchone())
        except sqlite3.Error as error: raise ObservationError('MEMORY_CORRUPT') from error

    def inspect_observation(self, observation_id):
        return self._read('SELECT * FROM records WHERE observation_id=?', (_query_id(observation_id),))

    def latest_reference(self, environment, *, host_device_id, boot_session_id, now_elapsed_ms, max_age_ms=2000):
        require(type(environment) is dict and set(environment) == {'app_package', 'app_build', 'environment_id', 'ui_revision', 'domain'}
                and all(identifier(v) for v in environment.values()), 'INVALID_QUERY')
        require(identifier(host_device_id) and identifier(boot_session_id) and type(now_elapsed_ms) is int
                and now_elapsed_ms >= 0 and type(max_age_ms) is int and 0 < max_age_ms <= 60000, 'INVALID_QUERY')
        record = self._read('SELECT * FROM records WHERE env_key=? AND host=? AND valid=1 ORDER BY revision DESC LIMIT 1',
                            (digest(environment), host_device_id))
        if record['status'] == 'NOT_FOUND': return record
        obs = record['observation']; age = now_elapsed_ms - obs['ended_elapsed_ms']
        status = 'HISTORICAL_SESSION' if obs['boot_session_id'] != boot_session_id else 'CLOCK_UNCONFIRMED' if age < 0 else \
                 'EXPIRED_REFERENCE' if age > max_age_ms else 'RECENT_MEMORY_REFERENCE'
        return dict(record, status=status, age_ms=age if age >= 0 else None)

    def search_in_observation(self, observation_id, **query):
        record = self.inspect_observation(observation_id)
        if record['status'] == 'NOT_FOUND': return record
        return dict(search_elements(record['page'], **query), memory_revision=record['memory_revision'], current_ui_confirmed=False)
