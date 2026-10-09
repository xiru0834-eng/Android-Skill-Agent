"""Immutable Scope and append-only provenance/cost ledger. No approval import."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3

from learning_scope import (HASH, ID, TEXT, ScopeError, array, bounded_document,
                            contracts, enum, integer, need, nullable, validate_scope)
from p21deps import canonical, digest

CATEGORIES = {'DEMONSTRATION': 'count', 'ANNOTATION': 'count', 'REVIEW': 'ms',
              'CORRECTION': 'ms', 'PRECONFIGURATION': 'ms'}
MAX_EVENTS = 1000
EVENT_SCHEMA = {'tag': 'kind', 'variants': {
    'HUMAN_COST': {'record': {
        'kind': {'const': 'HUMAN_COST'}, 'event_id': ID, 'activity_id': ID,
        'source_ids': array(ID, minimum=1), 'category': enum(*CATEGORIES),
        'actor': enum('HUMAN', 'AUTOMATED', 'UNKNOWN'),
        'amount': nullable(integer(2147483647)), 'unit': enum('count', 'ms'),
        'evidence_refs': array(TEXT, minimum=1), 'supersedes_event_id': nullable(ID),
    }},
    'GENERATION': {'record': {
        'kind': {'const': 'GENERATION'}, 'event_id': ID, 'source_ids': array(ID, minimum=1),
        'channel': enum('FAKE_MODEL', 'REAL_MODEL'), 'output_sha256': HASH, 'evidence_ref': TEXT,
    }},
}}


def validate_event(value, scope, prior):
    event = bounded_document(value)
    contracts._shape(event, EVENT_SCHEMA)
    sources = {source['source_id']: source for source in scope['sources']}
    need(set(event['source_ids']) <= set(sources), 'BAD_REFERENCE')
    need(event['event_id'] not in {old['event_id'] for old in prior}, 'DUPLICATE_ID')
    if event['kind'] == 'HUMAN_COST':
        need(event['unit'] == CATEGORIES[event['category']], 'COST_UNIT_MISMATCH')
        if event['category'] == 'DEMONSTRATION' and event['actor'] == 'HUMAN':
            need(all(sources[key]['actor'] != 'AUTOMATED' for key in event['source_ids']), 'ACTOR_MISMATCH')
        cost_events = {old['event_id']: old for old in prior if old['kind'] == 'HUMAN_COST'}
        previous = event['supersedes_event_id']
        if previous is None:
            need(event['activity_id'] not in {old['activity_id'] for old in cost_events.values()}, 'DUPLICATE_ACTIVITY')
        else:
            need(previous in cost_events, 'BAD_REFERENCE')
            need(previous not in {old['supersedes_event_id'] for old in cost_events.values()}, 'ALREADY_SUPERSEDED')
            original = cost_events[previous]
            for key in ('activity_id', 'category', 'actor', 'unit'):
                need(original[key] == event[key], 'COST_PROVENANCE_CHANGED')
            need(set(original['source_ids']) == set(event['source_ids']), 'COST_PROVENANCE_CHANGED')
    return event


def summarize_cost(scope, events):
    costs = [item for item in events if item['kind'] == 'HUMAN_COST']
    superseded = {item['supersedes_event_id'] for item in costs}
    active = [item for item in costs if item['event_id'] not in superseded]
    modes = {'DEMONSTRATION': 'DEMONSTRATION_ASSISTED', 'CORRECTION': 'EXPERT_CORRECTED',
             'PRECONFIGURATION': 'DOCUMENT_ASSISTED'}
    reports = {}
    for actor in ('HUMAN', 'AUTOMATED'):
        metrics = {}
        for category, unit in CATEGORIES.items():
            entries = [item for item in active if item['category'] == category]
            measured_actor = [item for item in entries if item['actor'] == actor]
            unknown = sum(item['actor'] == 'UNKNOWN' or (item['actor'] == actor and item['amount'] is None)
                          for item in entries)
            expected_sources = {source['source_id'] for source in scope['sources']
                                if source['mode'] == modes.get(category)
                                and (source['actor'] == 'AUTOMATED') == (actor == 'AUTOMATED')}
            covered = {key for item in measured_actor for key in item['source_ids']}
            missing = sorted(expected_sources - covered)
            total = sum(item['amount'] for item in measured_actor if item['amount'] is not None)
            complete = bool(measured_actor) and unknown == 0 and not missing
            metrics[category] = {'unit': unit, 'recorded_known_sum': total,
                                 'unmeasured_entries': unknown, 'missing_source_ids': missing,
                                 'complete': complete, 'total': total if complete else None}
        reports[actor] = metrics
    return reports['HUMAN'], reports['AUTOMATED']


class LearningLedger:
    def __init__(self, path):
        self.path = Path(path).resolve()

    @classmethod
    def create(cls, path, value):
        scope = validate_scope(value)
        need(scope['budgets']['max_storage_bytes'] >= 4096, 'STORAGE_BUDGET_EXCEEDED')
        target = Path(path)
        need(not target.is_symlink(), 'STORE_PATH_UNSAFE')
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            raise ScopeError('STORE_EXISTS') from None
        except OSError:
            raise ScopeError('STORE_IO_ERROR') from None
        store = cls(target)
        try:
            with closing(store._connect('rw')) as connection, connection:
                page_size = connection.execute('PRAGMA page_size').fetchone()[0]
                pages = scope['budgets']['max_storage_bytes'] // page_size
                connection.execute(f'PRAGMA max_page_count={pages}')
                connection.execute('CREATE TABLE scope_record(schema_version TEXT, raw TEXT, sha256 TEXT, revision INTEGER, head_sha256 TEXT)')
                connection.execute('CREATE TABLE events(sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE, raw TEXT, sha256 TEXT)')
                connection.execute('INSERT INTO scope_record VALUES (?,?,?,?,?)',
                                   ('p21_ledger_v1', canonical(scope), digest(scope), 0, digest(scope)))
        except sqlite3.Error as error:
            store._db_error(error)
        return store

    @classmethod
    def open(cls, path):
        need(not Path(path).is_symlink(), 'STORE_PATH_UNSAFE')
        store = cls(path)
        store.inspect()  # Never recreate missing/corrupt storage.
        return store

    def _connect(self, mode):
        need(self.path.is_file(), 'STORE_NOT_FOUND')
        need(self.path.stat().st_size <= 67108864, 'STORE_INPUT_LIMIT')
        return sqlite3.connect(self.path.as_uri() + '?mode=' + mode, uri=True, timeout=0.3)

    @staticmethod
    def _db_error(error):
        if 'full' in str(error).lower():
            code = 'STORAGE_BUDGET_EXCEEDED'
        elif 'locked' in str(error).lower():
            code = 'STORE_BUSY'
        else:
            code = 'STORE_CORRUPT'
        raise ScopeError(code) from None

    def _read(self, connection):
        records = connection.execute('SELECT schema_version,raw,sha256,revision,head_sha256 FROM scope_record LIMIT 2').fetchall()
        rows = records
        need(len(rows) == 1 and rows[0][0] == 'p21_ledger_v1', 'STORE_SCHEMA_ERROR')
        scope = validate_scope(rows[0][1])
        need(digest(scope) == rows[0][2], 'STORE_DIGEST_ERROR')
        rows = connection.execute('SELECT sequence,event_id,raw,sha256 FROM events ORDER BY sequence LIMIT ?',
                                  (MAX_EVENTS + 1,)).fetchall()
        need(len(rows) <= MAX_EVENTS, 'STORE_INPUT_LIMIT')
        previous_hash, events = digest(scope), []
        for expected, (sequence, event_id, raw, saved_hash) in enumerate(rows, 1):
            event = validate_event(raw, scope, events)
            need(sequence == expected and event['event_id'] == event_id, 'STORE_SEQUENCE_ERROR')
            previous_hash = digest({'sequence': sequence, 'parent': previous_hash, 'event': event})
            need(previous_hash == saved_hash, 'STORE_DIGEST_ERROR')
            events.append(event)
        need(records[0][3] == len(events) and records[0][4] == previous_hash, 'STORE_HEAD_ERROR')
        return scope, events, previous_hash

    def append(self, value, *, expected_revision):
        need(type(expected_revision) is int and 0 <= expected_revision <= MAX_EVENTS, 'INVALID_REVISION')
        event = bounded_document(value)
        try:
            with closing(self._connect('rw')) as connection, connection:
                connection.execute('BEGIN IMMEDIATE')
                scope, events, parent = self._read(connection)
                need(len(events) == expected_revision, 'STORE_CONFLICT')
                need(len(events) < MAX_EVENTS, 'STORE_EVENT_LIMIT')
                event = validate_event(event, scope, events)
                pages = scope['budgets']['max_storage_bytes'] // connection.execute('PRAGMA page_size').fetchone()[0]
                connection.execute(f'PRAGMA max_page_count={pages}')
                sequence = len(events) + 1
                head = digest({'sequence': sequence, 'parent': parent, 'event': event})
                connection.execute('INSERT INTO events VALUES (?,?,?,?)', (
                    sequence, event['event_id'], canonical(event), head))
                connection.execute('UPDATE scope_record SET revision=?,head_sha256=?', (sequence, head))
            return sequence
        except sqlite3.Error as error:
            self._db_error(error)

    def inspect(self):
        try:
            with closing(self._connect('ro')) as connection, connection:
                connection.execute('BEGIN')
                scope, events, head = self._read(connection)
        except sqlite3.Error as error:
            self._db_error(error)
        human, automated = summarize_cost(scope, events)
        return {'scope': scope, 'scope_hash': digest(scope), 'revision': len(events),
                'head_digest': head, 'events': events, 'human_cost': human, 'automated_cost': automated,
                'execution_authority': False, 'cost_completeness': 'RECORDED_ACTIVITIES_ONLY_NOT_ALL_HUMAN_EFFORT',
                'generation_evidence': 'DECLARED_METADATA_NOT_MODEL_CALL_PROOF',
                'database_bytes': self.path.stat().st_size, 'storage_budget': 'SQLITE_MAIN_DB_PAGES_ONLY'}
