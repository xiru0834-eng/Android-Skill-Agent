"""Inert versioned supplements over P1.4. No network, Android or durable authority.

FlowStore owns lifecycle. This SQLite database owns only immutable attachments
and append-only quarantine incidents. A cross-database save is deliberately
fail-closed: an orphan Flow is a DRAFT, not a retrievable knowledge package.
"""
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
from device_deps import flow_store, records, compiler, canonical, digest, verify_predecessor

MAX_BYTES = 1048576
MAX_SOURCES = 32
FIELDS = {'source_mode', 'model_original', 'human_revisions', 'human_cost', 'model_cost',
          'learning_materials', 'failures', 'limitations', 'historical_reports'}
SOURCE_MODES = {'REAL_ANDROID_SAVED_MATERIAL', 'REAL_MODEL_CANDIDATE', 'MANUAL',
                'HANDWRITTEN_TEST_FIXTURE', 'FAKE_MODEL_PROTOCOL_ONLY'}
FORBIDDEN = {'Task', 'authorization_ref', 'cancellation_token_ref', 'approved_raw_package_hash',
             'local_approval_verified', 'AccessibilityNode', 'Binder', 'input_permit', 'gesture_closure',
             'resume_authority', 'publication_state', 'published'}


class KnowledgeError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def need(ok, code):
    if not ok: raise KnowledgeError(code)


def inert_copy(value):
    """Bound JSON-only data; never deserialize executable Python objects."""
    def walk(item, depth=0):
        need(depth <= 64, 'KNOWLEDGE_DEPTH_LIMIT')
        if type(item) is dict:
            for key, child in item.items():
                need(type(key) is str and key not in FORBIDDEN, 'SUPPLEMENT_SECURITY_ERROR')
                if key in {'execution_authority', 'model_upload_authorized'}:
                    need(child is False, 'SUPPLEMENT_SECURITY_ERROR')
                if key == 'available_tools':
                    need(type(child) is list and not child, 'SUPPLEMENT_SECURITY_ERROR')
                walk(child, depth + 1)
        elif type(item) is list:
            for child in item: walk(child, depth + 1)
        else:
            need(item is None or type(item) in (str, int, float, bool), 'SUPPLEMENT_SECURITY_ERROR')
            if type(item) is float: need(math.isfinite(item), 'SUPPLEMENT_SCHEMA_ERROR')
    walk(value)
    text = canonical(value)
    need(len(text.encode('utf-8')) <= MAX_BYTES, 'KNOWLEDGE_SIZE_LIMIT')
    need(not re.search(r'sk-(?:proj-|ws-)?[A-Za-z0-9._-]{20,}', text), 'CREDENTIAL_CONTENT_REJECTED')
    return json.loads(text)


def validate_supplement(value):
    need(type(value) is dict and set(value) == FIELDS, 'SUPPLEMENT_SCHEMA_ERROR')
    value = inert_copy(value)
    need(type(value['source_mode']) is str and value['source_mode'] in SOURCE_MODES and
         (value['model_original'] is None or type(value['model_original']) is str), 'SUPPLEMENT_SCHEMA_ERROR')
    for field in ('human_revisions', 'failures', 'limitations', 'historical_reports'):
        need(type(value[field]) is list, 'SUPPLEMENT_SCHEMA_ERROR')
    materials = value['learning_materials']
    need(type(materials) is dict and set(materials) == {'pages', 'navigation', 'documents'}
         and all(type(v) is list for v in materials.values()), 'SUPPLEMENT_SCHEMA_ERROR')
    human, model = value['human_cost'], value['model_cost']
    need(type(human) is dict and set(human) == {'actions', 'minutes'}
         and type(model) is dict and set(model) == {'calls', 'reported_usd'}, 'COST_SCHEMA_ERROR')
    for v, types in ((human['actions'], (int,)), (human['minutes'], (int, float)), (model['calls'], (int,))):
        need(v is None or type(v) in types and 0 <= v <= 1000000000, 'COST_SCHEMA_ERROR')
    usd = model['reported_usd']
    need(usd is None or type(usd) is str and re.fullmatch(r'\d{1,10}(?:\.\d{1,10})?', usd), 'COST_SCHEMA_ERROR')
    return value


def source_ref(path, approved_roots):
    """Caller-approved local files only; package/model paths are not authority."""
    original = Path(path)
    need(original.is_absolute() and not original.is_symlink(), 'SOURCE_PATH_NOT_ALLOWED')
    path = original.resolve()
    need(any(path.is_relative_to(Path(root).resolve()) for root in approved_roots), 'SOURCE_PATH_NOT_ALLOWED')
    with path.open('rb') as stream: raw = stream.read(MAX_BYTES + 1)
    need(len(raw) <= MAX_BYTES, 'SOURCE_SIZE_LIMIT')
    return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


class KnowledgeLibrary:
    FILENAME = 'knowledge-supplements-v1.sqlite3'
    SCHEMA = 'p34_inert_knowledge_v1'

    def __init__(self, root, flows, db, approved_roots):
        need(type(approved_roots) in (list, tuple) and approved_roots, 'APPROVED_SOURCE_ROOTS_REQUIRED')
        self.root, self.flows, self.db = Path(root).resolve(), flows, db
        self.approved_roots = tuple(Path(p).resolve() for p in approved_roots)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=500'); db.execute('PRAGMA synchronous=FULL')

    @classmethod
    def create(cls, root, *, approved_roots):
        need(type(approved_roots) in (list, tuple) and approved_roots, 'APPROVED_SOURCE_ROOTS_REQUIRED')
        root = Path(root).resolve()
        need(not (root / cls.FILENAME).exists(), 'KNOWLEDGE_ALREADY_EXISTS')
        flows = flow_store.FlowStore.create(root)
        db = None
        try:
            fd = os.open(root / cls.FILENAME, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
            db = sqlite3.connect(root / cls.FILENAME, isolation_level=None)
            instance = cls(root, flows, db, approved_roots)
            with instance.transaction():
                db.execute('CREATE TABLE metadata(name TEXT PRIMARY KEY,value TEXT NOT NULL)')
                db.execute('INSERT INTO metadata VALUES(?,?)', ('schema', cls.SCHEMA))
                db.execute('CREATE TABLE attachments(key TEXT PRIMARY KEY,body_json TEXT NOT NULL,sha256 TEXT NOT NULL)')
                db.execute('CREATE TABLE incidents(key TEXT NOT NULL,revision INTEGER NOT NULL,body_json TEXT NOT NULL,sha256 TEXT NOT NULL,PRIMARY KEY(key,revision))')
            return instance
        except Exception:
            if db: db.close()
            flows.close()
            raise  # Incomplete files remain diagnostic evidence, never silently replaced.

    @classmethod
    def open(cls, root, *, approved_roots):
        root = Path(root).resolve(); path = root / cls.FILENAME
        need(path.is_file() and not path.is_symlink(), 'KNOWLEDGE_NOT_FOUND')
        flows = flow_store.FlowStore.open(root); db = None
        try:
            db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, isolation_level=None)
            instance = cls(root, flows, db, approved_roots)
            need(db.execute('PRAGMA quick_check').fetchone()[0] == 'ok', 'KNOWLEDGE_CORRUPT')
            need(dict(db.execute('SELECT name,value FROM metadata')) == {'schema': cls.SCHEMA}, 'KNOWLEDGE_SCHEMA_UNSUPPORTED')
            return instance
        except Exception as error:
            if db: db.close()
            flows.close()
            if isinstance(error, sqlite3.Error): raise KnowledgeError('KNOWLEDGE_CORRUPT') from None
            raise

    def close(self):
        self.db.close(); self.flows.close()

    @contextmanager
    def transaction(self, write=True):
        try:
            self.db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield
            self.db.execute('COMMIT')
        except Exception as error:
            if self.db.in_transaction: self.db.execute('ROLLBACK')
            if isinstance(error, sqlite3.Error): raise KnowledgeError('KNOWLEDGE_STORAGE_ERROR') from None
            raise

    def _source(self, path):
        return source_ref(path, self.approved_roots)

    @staticmethod
    def _source_shape(refs):
        need(type(refs) is list and len(refs) <= MAX_SOURCES, 'SOURCE_REFERENCE_ERROR')
        for ref in refs:
            need(type(ref) is dict and set(ref) == {'path', 'sha256', 'bytes'}
                 and type(ref['path']) is str and type(ref['sha256']) is str
                 and re.fullmatch(r'[a-f0-9]{64}', ref['sha256'])
                 and type(ref['bytes']) is int and 0 <= ref['bytes'] <= MAX_BYTES, 'SOURCE_REFERENCE_ERROR')
        need(len({r['path'] for r in refs}) == len(refs), 'SOURCE_REFERENCE_ERROR')

    def save_draft(self, raw, package, supplement, expected_head_revision, *, source_paths):
        metadata = validate_supplement(supplement)
        need(type(source_paths) in (list, tuple) and len(source_paths) <= MAX_SOURCES, 'SOURCE_REFERENCE_ERROR')
        refs = [self._source(p) for p in source_paths]
        return self._save(raw, package, metadata, expected_head_revision, refs)

    def _save(self, raw, package, supplement, expected_head_revision, refs):
        self._source_shape(refs)
        # No publication occurs between Flow insertion and attachment commit.
        record = self.flows.save_draft(raw, package, expected_head_revision)
        body = {'schema': self.SCHEMA, 'flow_key': record['key'], 'flow_version_sha256': record['sha256'],
                'supplement': supplement, 'source_refs': refs}
        with self.transaction():
            self.db.execute('INSERT INTO attachments VALUES(?,?,?)', (record['key'], canonical(body), digest(body)))
        return self.inspect(record['key'])

    @staticmethod
    def _decode(row):
        need(len(row['body_json'].encode('utf-8')) <= MAX_BYTES + 16384, 'KNOWLEDGE_SIZE_LIMIT')
        try: value = json.loads(row['body_json'])
        except (ValueError, RecursionError): raise KnowledgeError('KNOWLEDGE_CORRUPT') from None
        need(digest(value) == row['sha256'], 'KNOWLEDGE_DIGEST_ERROR')
        return value

    def _read(self, key):
        row = self.db.execute('SELECT * FROM attachments WHERE key=?', (key,)).fetchone()
        need(row is not None, 'KNOWLEDGE_NOT_FOUND')
        body = self._decode(row)
        need(type(body) is dict and set(body) == {'schema', 'flow_key', 'flow_version_sha256', 'supplement', 'source_refs'}
             and body['schema'] == self.SCHEMA and body['flow_key'] == key, 'KNOWLEDGE_CORRUPT')
        validate_supplement(body['supplement']); self._source_shape(body['source_refs'])
        record = self.flows.load(key)
        need(body['flow_version_sha256'] == record['sha256'], 'FLOW_VERSION_MISMATCH')
        incidents, previous = [], None
        for n, row in enumerate(self.db.execute('SELECT * FROM incidents WHERE key=? ORDER BY revision', (key,)), 1):
            event = self._decode(row)
            need(type(event) is dict and set(event) == {'key', 'revision', 'reason', 'evidence_id', 'previous_hash', 'execution_authority'}
                 and event.get('previous_hash') == previous and type(event.get('revision')) is int
                 and event['revision'] == row['revision'] == n and event.get('key') == key
                 and event['reason'] in {'VALIDATION_FAILURE', 'DEPENDENCY_CHANGE', 'EVIDENCE_DAMAGE', 'OPERATOR_REVOKED'}
                 and event['execution_authority'] is False
                 and (event['evidence_id'] is None or event['evidence_id'] in {s['evidence_id'] for s in record['scopes']}),
                 'INCIDENT_CHAIN_ERROR')
            incidents.append(event); previous = row['sha256']
        return record, body, incidents

    def inspect(self, key):
        need(type(key) is str and 1 <= len(key) <= 160, 'KNOWLEDGE_NOT_FOUND')
        with self.transaction(False): record, body, incidents = self._read(key)
        integrity = 'PASS'
        for ref in body['source_refs']:
            try:
                if self._source(ref['path']) != ref: integrity = 'SOURCE_CHANGED'; break
            except (OSError, KnowledgeError): integrity = 'SOURCE_UNAVAILABLE'; break
        try: verify_predecessor()
        except (ValueError, OSError, KeyError, TypeError): integrity = 'DEPENDENCY_CHANGED'
        required_calls = sum(s['op'] == 'call' for s in record['flow']['steps'])
        points = [{**scope, 'setting_trial': required_calls > 0 and len(scope['ordered_calls']) == required_calls,
                   'required_call_count': required_calls, 'executed_call_count': len(scope['ordered_calls']),
                   'branch_coverage': 'UNKNOWN_NOT_GENERALIZED'} for scope in record['scopes']]
        whole = any(e['evidence_id'] is None for e in incidents)
        excluded = {e['evidence_id'] for e in incidents}
        eligible = [p for p in points if p['evidence_id'] not in excluded and not whole and integrity == 'PASS']
        setting = [p for p in eligible if p['setting_trial']]
        logic = record['state'] == 'PUBLISHED' and bool(setting)
        formal = logic and body['supplement']['source_mode']=='REAL_MODEL_CANDIDATE' and all(
            p['channel']==flow_store.FlowStore.CHANNEL and p.get('device_execution_verified') is True for p in setting)
        return {'key': key, 'version_sha256': record['sha256'], 'flow': record['flow'], 'package': record['package'],
                'flow_state': record['state'], 'flow_revision': record['revision'], 'flow_history': record['history'],
                'supplement': body['supplement'], 'source_refs': body['source_refs'], 'integrity': integrity,
                'binding_states': [{'binding_id': b['id'], 'state': 'CANDIDATE', 'capability_verified': False}
                                   for b in record['package']['bindings']],
                'static_support': {'inputs': record['flow']['inputs'], 'dependencies': record['dependencies'],
                                   'claim': 'DECLARED_DOMAIN_NOT_EXECUTED_DOMAIN'},
                'actual_points': points, 'eligible_points': eligible, 'incidents': incidents,
                'parameter_domain_verified': False, 'future_reliability_proven': False,
                'logic_retrievable': False, 'formal_retrievable': formal, 'execution_authority': False,
                'available_tools': [], 'formal_gate': 'LOCAL_TASK_AUTHORIZATION_REQUIRED' if formal else 'REAL_FLOW_VERIFICATION_REQUIRED'}

    def record_validation(self, key, expected_revision, evidence):
        out = self.inspect(key)
        need(out['integrity'] == 'PASS' and not any(e['evidence_id'] is None for e in out['incidents']), 'KNOWLEDGE_QUARANTINED')
        # The old store authenticates the in-process RunEvidence, hashes and channel.
        return self.flows.record_validation(key, expected_revision, evidence)

    def publish_logic(self, key, expected_revision, authority):
        out = self.inspect(key)
        need(out['integrity'] == 'PASS', 'KNOWLEDGE_QUARANTINED')
        need(type(authority) is records.PublishAuthority, 'PUBLISH_AUTHORITY_REQUIRED')
        need(any(p['setting_trial'] and p['environment_hash'] == authority.environment_hash for p in out['eligible_points']),
             'SETTING_CAPABILITY_NOT_TRIALED')
        self.flows.publish(key, expected_revision, authority)
        return self.inspect(key)

    def publish_formal(self, key, expected_revision, authority):
        out=self.inspect(key)
        need(out['supplement']['source_mode']=='REAL_MODEL_CANDIDATE','REAL_MODEL_ORIGIN_REQUIRED')
        need(type(authority) is records.PublishAuthority and authority.evidence_channel==flow_store.FlowStore.CHANNEL,
             'REAL_FLOW_VERIFICATION_REQUIRED')
        self.publish_logic(key,expected_revision,authority)
        result=self.inspect(key)
        need(result['formal_retrievable'],'REAL_FLOW_VERIFICATION_REQUIRED')
        return result

    def list_knowledge(self, channel):
        need(channel in {'FORMAL', 'LOGIC_SIMULATION'}, 'INVALID_QUERY_CHANNEL')
        keys = [r[0] for r in self.db.execute('SELECT key FROM attachments ORDER BY key')]
        records_ = [self.inspect(key) for key in keys]
        return [r for r in records_ if r['formal_retrievable' if channel == 'FORMAL' else 'logic_retrievable']]

    def assess_task(self, key, task):
        out = self.inspect(key)
        result = {'execution_authority': False, 'task_success': False, 'exact_point_previously_observed': False}
        if out['integrity'] != 'PASS' or any(e['evidence_id'] is None for e in out['incidents']):
            return {**result, 'status': 'QUARANTINED'}
        try: compiler.compile_flow(out['flow'], out['package'], task, None)
        except compiler.CompileError as error: return {**result, 'status': 'REJECTED', 'failure': error.receipt()}
        seen = any(p['inputs'] == task['inputs'] for p in out['eligible_points'])
        return {**result, 'status': 'STATIC_COMPATIBLE_REQUIRES_LIVE_POLICY_AND_VERIFICATION',
                'exact_point_previously_observed': seen, 'initial_state_not_assessed': True}

    def quarantine(self, key, reason, *, evidence_id=None):
        need(reason in {'VALIDATION_FAILURE', 'DEPENDENCY_CHANGE', 'EVIDENCE_DAMAGE', 'OPERATOR_REVOKED'}, 'INVALID_INCIDENT_REASON')
        with self.transaction():
            record, body, incidents = self._read(key)
            need(evidence_id is None or type(evidence_id) is str and
                 evidence_id in {s['evidence_id'] for s in record['scopes']}, 'UNKNOWN_EVIDENCE_SCOPE')
            previous = digest(incidents[-1]) if incidents else None
            event = {'key': key, 'revision': len(incidents) + 1, 'reason': reason,
                     'evidence_id': evidence_id, 'previous_hash': previous, 'execution_authority': False}
            self.db.execute('INSERT INTO incidents VALUES(?,?,?,?)', (key, event['revision'], canonical(event), digest(event)))
        return self.inspect(key)

    def export(self, key):
        out = self.inspect(key)
        supplement = json.loads(canonical(out['supplement']))
        # Historical scopes retain learning evidence, not live validation objects.
        supplement['historical_reports'] += out['actual_points']
        supplement['failures'] += out['incidents']
        core = {'format': 'p34_inert_knowledge_export_v1', 'flow_export': self.flows.export_knowledge(key),
                'supplement': supplement, 'source_refs': out['source_refs']}
        return {**core, 'digest': digest(core)}

    def import_knowledge(self, envelope, expected_head_revision):
        need(type(envelope) is dict and set(envelope) == {'format', 'flow_export', 'supplement', 'source_refs', 'digest'}, 'EXPORT_SCHEMA_ERROR')
        core = {k: v for k, v in envelope.items() if k != 'digest'}
        need(digest(core) == envelope['digest'], 'EXPORT_DIGEST_ERROR')
        need(core['format'] == 'p34_inert_knowledge_export_v1', 'EXPORT_SCHEMA_ERROR')
        metadata = validate_supplement(core['supplement']); self._source_shape(core['source_refs'])
        exported = core['flow_export']
        need(type(exported) is dict and set(exported) == {'format', 'flow_raw', 'package', 'sha256'}, 'EXPORT_SCHEMA_ERROR')
        need(exported['format'] == 'flow_knowledge_export_v1'
             and digest({k: v for k, v in exported.items() if k != 'sha256'}) == exported['sha256'], 'EXPORT_DIGEST_ERROR')
        return self._save(exported['flow_raw'], exported['package'], metadata, expected_head_revision, core['source_refs'])
