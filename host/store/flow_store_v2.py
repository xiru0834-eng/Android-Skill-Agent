"""Versioned knowledge storage; no Task/approval/node or resume capability.

Atomic SQLite transactions protect all versions/events/head updates. Hashes
detect accidental corruption, not forged local authority. No evidence ref is
dereferenced. Every execution must acquire independent live host policy.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from p14deps import contracts, compiler, canonical, digest
from records import RunEvidence, PublishAuthority


class StoreError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def need(ok, code):
    if not ok:
        raise StoreError(code)


def _parse_draft(raw, package):
    try:
        need(type(raw) is str, 'DRAFT_TYPE_ERROR')
        # Refuse obvious API key material; never store task credentials as drafts.
        need(not re.search(r'sk-(?:proj-|ws-)[A-Za-z0-9._-]{8}', raw), 'CREDENTIAL_CONTENT_REJECTED')
        flow = contracts.parse_document(raw)
        contracts.validate_document(flow)
        contracts.validate_document(package)
        need(not re.search(r'sk-(?:proj-|ws-)[A-Za-z0-9._-]{8}', canonical(package)), 'CREDENTIAL_CONTENT_REJECTED')
        need(flow['kind'] == 'FlowSkill' and package['kind'] == 'AppKnowledgePackage', 'DRAFT_TYPE_ERROR')
        need(flow['verified_scope'] == [], 'MODEL_VALIDATION_CLAIM')
        need({'id': flow['id'], 'version': flow['version']} in package['flow_refs'], 'BAD_REFERENCE')
        need(set(flow['evidence_refs']) <= {r['id'] for r in package['evidence']}, 'BAD_REFERENCE')
        return flow
    except contracts.ContractError as error:
        raise StoreError(error.code) from None


def _diff(old, new, prefix=''):
    if type(old) is dict and type(new) is dict:
        return [p for key in sorted(set(old) | set(new))
                for p in ([prefix + '/' + key] if key not in old or key not in new
                          else _diff(old[key], new[key], prefix + '/' + key))]
    return [] if type(old) is type(new) and old == new else [prefix]


class FlowStore:
    FILENAME = 'flow-knowledge-android-v2.sqlite3'
    SCHEMA = 'p14_flow_store_android_v2'
    MODE = 'REAL_ANDROID_CANDIDATE'
    CHANNEL = 'REAL_ANDROID_FLOW_VALIDATION'

    def __init__(self, root, db):
        self.root, self.db = Path(root).resolve(), db
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=500')

    @classmethod
    def create(cls, root):
        root = Path(root).resolve()
        root.mkdir(parents=True, exist_ok=True)
        path = root / cls.FILENAME
        try:
            descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        except FileExistsError:
            raise StoreError('STORE_ALREADY_EXISTS') from None
        instance = cls(root, sqlite3.connect(path, isolation_level=None))
        try:
            instance.db.execute('PRAGMA synchronous=FULL')
            with instance._transaction():
                instance.db.execute('CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT NOT NULL)')
                instance.db.executemany('INSERT INTO metadata VALUES(?,?)', [('schema', cls.SCHEMA), ('mode', cls.MODE)])
                instance.db.execute('CREATE TABLE versions(key TEXT PRIMARY KEY,flow_id TEXT NOT NULL,body_json TEXT NOT NULL,sha256 TEXT NOT NULL)')
                instance.db.execute('CREATE TABLE heads(flow_id TEXT PRIMARY KEY,key TEXT NOT NULL,revision INTEGER NOT NULL)')
                instance.db.execute('CREATE TABLE events(key TEXT NOT NULL,revision INTEGER NOT NULL,body_json TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(key,revision))')
            return instance
        except Exception:
            instance.close()
            raise  # Preserve incomplete file for diagnostics, never silently replace it.

    @classmethod
    def open(cls, root):
        root = Path(root).resolve()
        path = root / cls.FILENAME
        need(path.is_file() and not path.is_symlink(), 'STORE_NOT_FOUND')
        instance = None
        try:
            db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, isolation_level=None)
            instance = cls(root, db)
            need(db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'STORE_CORRUPT')
            metadata = dict(db.execute('SELECT name,value FROM metadata').fetchall())
            need(metadata == {'schema': cls.SCHEMA, 'mode': cls.MODE}, 'STORE_SCHEMA_UNSUPPORTED')
            return instance
        except (sqlite3.Error, StoreError) as error:
            if instance:
                instance.close()
            raise error if isinstance(error, StoreError) else StoreError('STORE_CORRUPT') from None

    def close(self):
        self.db.close()

    @contextmanager
    def _transaction(self, write=True):
        try:
            self.db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield
            self.db.execute('COMMIT')
        except Exception as error:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            if isinstance(error, sqlite3.Error):
                code = getattr(error, 'sqlite_errorcode', 0) & 255
                raise StoreError('STORE_BUSY' if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED)
                                 else 'STORE_STORAGE_ERROR') from None
            raise

    @staticmethod
    def _decode(row):
        try:
            need(len(row['body_json'].encode('utf-8')) <= 262144, 'STORE_RECORD_LIMIT')
            value = json.loads(row['body_json'])
            need(digest(value) == row['sha256'], 'STORE_DIGEST_ERROR')
            return value
        except (ValueError, TypeError, RecursionError) as error:
            raise error if isinstance(error, StoreError) else StoreError('STORE_DIGEST_ERROR') from None

    def _event(self, key, revision, state, payload, previous=''):
        need(revision <= 1024, 'STORE_EVENT_LIMIT')
        body = {'version_key': key, 'revision': revision, 'state': state, 'payload': payload,
                'previous_hash': previous, 'recorded_utc_ns': time.time_ns()}
        self.db.execute('INSERT INTO events VALUES(?,?,?,?)', (key, revision, canonical(body), digest(body)))

    def _load(self, key):
        need(type(key) is str and 0 < len(key) <= 160, 'VERSION_KEY_ERROR')
        row = self.db.execute('SELECT * FROM versions WHERE key=?', (key,)).fetchone()
        need(row is not None, 'VERSION_NOT_FOUND')
        body = self._decode(row)
        try:
            flow = _parse_draft(body['flow_raw'], body['package'])
            need(key == flow['id'] + '@' + flow['version'] and row['flow_id'] == flow['id'], 'STORE_DIGEST_ERROR')
            if body['parent_key']:
                parent = self.db.execute('SELECT * FROM versions WHERE key=?', (body['parent_key'],)).fetchone()
                need(parent is not None and parent['sha256'] == body['parent_hash'], 'STORE_DEPENDENCY_ERROR')
                self._decode(parent)
            rows = self.db.execute('SELECT * FROM events WHERE key=? ORDER BY revision', (key,)).fetchall()
            need(1 <= len(rows) <= 1024, 'STORE_EVENT_ERROR')
            previous, state, scopes, history = '', None, [], []
            allowed = {None: {'DRAFT'}, 'DRAFT': {'CHECKED', 'INVALIDATED', 'REVOKED'},
                       'CHECKED': {'VALIDATED_SCOPE', 'INVALIDATED', 'REVOKED'},
                       'VALIDATED_SCOPE': {'VALIDATED_SCOPE', 'PUBLISHED', 'INVALIDATED', 'REVOKED'},
                       'PUBLISHED': {'INVALIDATED', 'REVOKED'}, 'INVALIDATED': set(), 'REVOKED': set()}
            for revision, event_row in enumerate(rows, 1):
                event = self._decode(event_row)
                need(event['version_key'] == key and event['revision'] == revision and
                     event['previous_hash'] == previous and event['state'] in allowed[state], 'STORE_EVENT_ERROR')
                previous, state = event_row['sha256'], event['state']
                if state == 'VALIDATED_SCOPE':
                    scope = event['payload']['scope']
                    need(scope['flow_hash'] == digest(flow) and scope['package_hash'] == digest(body['package']) and
                         scope['channel'] == self.CHANNEL and scope['sequence_verified'] is True,
                         'STORE_SCOPE_ERROR')
                    scopes.append(scope)
                history.append(event)
            return {**body, 'key': key, 'sha256': row['sha256'], 'flow': flow, 'state': state,
                    'revision': len(rows), 'scopes': scopes, 'history': history,
                    'execution_authority': False, 'device_execution_verified': bool(scopes),
                    'resume_authority': False, 'store_mode': self.MODE}
        except (KeyError, TypeError, IndexError) as error:
            raise StoreError('STORE_RECORD_ERROR') from None

    def load(self, key):
        if self.db.in_transaction:
            return self._load(key)
        with self._transaction(False):
            return self._load(key)

    def list_versions(self):
        with self._transaction(False):
            return [self._load(row[0]) for row in self.db.execute('SELECT key FROM versions ORDER BY key').fetchall()]

    def save_draft(self, raw, package, expected_head_revision):
        flow = _parse_draft(raw, package)
        need(type(expected_head_revision) is int and expected_head_revision >= 0, 'REVISION_TYPE_ERROR')
        key = flow['id'] + '@' + flow['version']
        with self._transaction():
            need(self.db.execute('SELECT 1 FROM versions WHERE key=?', (key,)).fetchone() is None, 'VERSION_ALREADY_EXISTS')
            head = self.db.execute('SELECT * FROM heads WHERE flow_id=?', (flow['id'],)).fetchone()
            need(expected_head_revision == (head['revision'] if head else 0), 'REVISION_CONFLICT')
            parent = self._load(head['key']) if head else None
            if parent:
                need(tuple(map(int, flow['version'].split('.'))) > tuple(map(int, parent['flow']['version'].split('.'))),
                     'VERSION_NOT_NEWER')
            body = {'flow_raw': raw, 'package': package, 'parent_key': parent['key'] if parent else None,
                    'parent_hash': parent['sha256'] if parent else None,
                    'diff': _diff({'flow': parent['flow'], 'package': parent['package']} if parent else {},
                                  {'flow': flow, 'package': package}),
                    'dependencies': flow['dependencies'], 'evidence_refs': flow['evidence_refs']}
            need(len(canonical(body).encode('utf-8')) <= 262144, 'STORE_RECORD_LIMIT')
            self.db.execute('INSERT INTO versions VALUES(?,?,?,?)', (key, flow['id'], canonical(body), digest(body)))
            self._event(key, 1, 'DRAFT', {'execution_authority': False})
            self.db.execute('INSERT INTO heads VALUES(?,?,?) ON CONFLICT(flow_id) DO UPDATE SET key=excluded.key,revision=excluded.revision',
                            (flow['id'], key, expected_head_revision + 1))
            return self._load(key)

    def _transition(self, key, expected_revision, from_states, state, build_payload):
        need(type(expected_revision) is int and expected_revision >= 1, 'REVISION_TYPE_ERROR')
        with self._transaction():
            value = self._load(key)
            need(value['revision'] == expected_revision, 'REVISION_CONFLICT')
            need(value['state'] in from_states, 'STATE_TRANSITION_ERROR')
            payload = build_payload(value)
            self._event(key, expected_revision + 1, state, payload, digest(value['history'][-1]))
            return self._load(key)

    def check(self, key, expected_revision, task, profile=None):
        def compile_summary(value):
            try:
                plan = compiler.compile_flow(value['flow'], value['package'], task, profile).to_dict()
            except compiler.CompileError as error:
                raise StoreError(error.code) from None
            return {'status': plan['status'], 'environment_hash': plan['environment_hash'],
                    'flow_hash': plan['flow_hash'], 'package_hash': plan['package_hash'],
                    'registry_hash': plan['registry_hash'], 'blocking_unknowns': plan['blocking_unknowns'],
                    'execution_authority': False}
        return self._transition(key, expected_revision, {'DRAFT'}, 'CHECKED', compile_summary)

    def record_validation(self, key, expected_revision, evidence):
        need(type(evidence) is RunEvidence, 'TRUSTED_ADAPTER_EVIDENCE_REQUIRED')
        scope = evidence.to_dict()
        def verified(value):
            need(scope['channel'] == self.CHANNEL and scope['sequence_verified'] is True and
                 scope['version_sha256'] == value['sha256'] and scope['flow_hash'] == digest(value['flow']) and
                 scope['package_hash'] == digest(value['package']), 'VALIDATION_EVIDENCE_MISMATCH')
            return {'scope': scope, 'execution_authority': False}
        return self._transition(key, expected_revision, {'CHECKED', 'VALIDATED_SCOPE'}, 'VALIDATED_SCOPE', verified)

    def publish(self, key, expected_revision, authority):
        need(type(authority) is PublishAuthority and authority.confirmed is True and
             authority.version_key == key and type(authority.operator_id) is str and
             0 < len(authority.operator_id) <= 128, 'PUBLICATION_AUTHORITY_REQUIRED')
        need(authority.evidence_channel == self.CHANNEL, 'REAL_DEVICE_VALIDATION_REQUIRED')
        def approved(value):
            need(any(scope['environment_hash'] == authority.environment_hash and
                     scope['channel'] == authority.evidence_channel for scope in value['scopes']), 'VALIDATED_SCOPE_REQUIRED')
            return {'operator_id': authority.operator_id, 'environment_hash': authority.environment_hash,
                    'evidence_channel': authority.evidence_channel, 'execution_authority': False}
        return self._transition(key, expected_revision, {'VALIDATED_SCOPE'}, 'PUBLISHED', approved)

    def invalidate(self, key, expected_revision, state, reason):
        need(state in {'INVALIDATED', 'REVOKED'} and type(reason) is str and
             re.fullmatch(r'[a-zA-Z0-9_.:-]{1,128}', reason) is not None, 'INVALIDATION_INPUT_ERROR')
        return self._transition(key, expected_revision, {'DRAFT', 'CHECKED', 'VALIDATED_SCOPE', 'PUBLISHED'}, state,
                                lambda _: {'reason': reason, 'execution_authority': False})

    def export_knowledge(self, key):
        value = self.load(key)
        core = {'format': 'flow_knowledge_export_v1', 'flow_raw': value['flow_raw'], 'package': value['package']}
        return {**core, 'sha256': digest(core)}  # No approvals, scopes, cursor or Task.

    def import_knowledge(self, envelope, expected_head_revision):
        need(type(envelope) is dict and set(envelope) == {'format', 'flow_raw', 'package', 'sha256'} and
             envelope['format'] == 'flow_knowledge_export_v1', 'IMPORT_FORMAT_ERROR')
        core = {k: v for k, v in envelope.items() if k != 'sha256'}
        try:
            need(digest(core) == envelope['sha256'], 'IMPORT_DIGEST_ERROR')
        except (TypeError, ValueError, RecursionError) as error:
            raise error if isinstance(error, StoreError) else StoreError('IMPORT_FORMAT_ERROR') from None
        return self.save_draft(envelope['flow_raw'], envelope['package'], expected_head_revision)
