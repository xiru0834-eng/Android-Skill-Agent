"""Fault injection targets the new attachment boundary, not predecessor files."""
import json
from pathlib import Path
from unittest.mock import patch
from test_publication import PublicationTests, supplement
from knowledge import KnowledgeError
from p34deps import canonical, digest


class FaultTests(PublicationTests):
    # Override discovery of inherited methods: only new tests in this class
    # are registered by load_tests below; helpers remain reusable.
    def test_F01_dependency_drift_quarantines_knowledge(self):
        key = self.published()
        with patch('knowledge.verify_predecessor', side_effect=ValueError('PREDECESSOR_FROZEN_DRIFT')):
            out = self.library.inspect(key)
        self.assertEqual(out['integrity'], 'DEPENDENCY_CHANGED')
        self.assertFalse(out['logic_retrievable']); self.assertEqual(len(out['actual_points']), 2)

    def test_F02_invalid_source_mode_has_explicit_error(self):
        for value in (None, [], {}, True, 3, 'invented'):
            with self.subTest(value=value):
                meta = supplement(); meta['source_mode'] = value
                self.reject('SUPPLEMENT_SCHEMA_ERROR', lambda: self.draft(meta))

    def test_F03_nested_authority_and_live_objects_are_rejected(self):
        for item in ({'authorization_ref': 'old'}, {'execution_authority': True}, {'AccessibilityNode': object()},
                     {'gesture_closure': lambda: None}, {'value': float('nan')}, {'value': float('inf')}):
            with self.subTest(kind=next(iter(item))):
                meta = supplement(); meta['learning_materials']['pages'] = [item]
                with self.assertRaises(KnowledgeError): self.draft(meta)
        self.assertEqual(self.library.flows.list_versions(), [])

    def test_F04_missing_or_unapproved_evidence_does_not_insert_flow(self):
        for path in (self.root / 'missing', Path('relative.json'), Path('C:/Windows/win.ini')):
            with self.subTest(path=str(path)):
                with self.assertRaises((KnowledgeError, OSError)):
                    self.library.save_draft(canonical(self.flow), self.package, supplement(), 0, source_paths=[path])
        self.assertEqual(self.library.flows.list_versions(), [])

    def test_F05_source_deleted_is_quarantined(self):
        key = self.published(); self.source.unlink()
        out = self.library.inspect(key)
        self.assertEqual(out['integrity'], 'SOURCE_UNAVAILABLE'); self.assertFalse(out['logic_retrievable'])

    def test_F06_duplicate_and_too_many_sources_rejected(self):
        for paths in ([self.source, self.source], [self.source] * 33):
            with self.subTest(count=len(paths)):
                self.reject('SOURCE_REFERENCE_ERROR', lambda: self.library.save_draft(
                    canonical(self.flow), self.package, supplement(), 0, source_paths=paths))
        self.assertEqual(self.library.flows.list_versions(), [])

    def test_F07_truncated_or_wrong_digest_attachment_does_not_clear_store(self):
        key = self.published()
        self.library.db.execute('UPDATE attachments SET body_json=? WHERE key=?', ('{"broken":', key))
        self.reject('KNOWLEDGE_CORRUPT', lambda: self.library.inspect(key))
        self.assertEqual(self.library.flows.load(key)['state'], 'PUBLISHED')

    def test_F08_structurally_malformed_incident_is_explicit(self):
        key = self.published(); value = []
        self.library.db.execute('INSERT INTO incidents VALUES(?,?,?,?)', (key, 1, canonical(value), digest(value)))
        self.reject('INCIDENT_CHAIN_ERROR', lambda: self.library.inspect(key))

    def test_F09_incident_hash_chain_detects_tampering(self):
        key = self.published(); self.library.quarantine(key, 'OPERATOR_REVOKED')
        row = self.library.db.execute('SELECT * FROM incidents WHERE key=?', (key,)).fetchone()
        value = json.loads(row['body_json']); value['previous_hash'] = 'invented'
        self.library.db.execute('UPDATE incidents SET body_json=?,sha256=? WHERE key=?', (canonical(value), digest(value), key))
        self.reject('INCIDENT_CHAIN_ERROR', lambda: self.library.inspect(key))

    def test_F10_false_failure_scope_and_reason_rejected(self):
        key = self.published()
        self.reject('UNKNOWN_EVIDENCE_SCOPE', lambda: self.library.quarantine(key, 'VALIDATION_FAILURE', evidence_id='unobserved'))
        self.reject('INVALID_INCIDENT_REASON', lambda: self.library.quarantine(key, 'RESET_EVERYTHING'))

    def test_F11_orphan_draft_is_not_searchable_or_publishable(self):
        row = self.library.flows.save_draft(canonical(self.flow), self.package, 0)
        self.assertEqual(self.library.list_knowledge('LOGIC_SIMULATION'), [])
        self.reject('KNOWLEDGE_NOT_FOUND', lambda: self.library.publish_formal(row['key']))
        self.assertEqual(self.library.flows.load(row['key'])['state'], 'DRAFT')

    def test_F12_bad_parameter_does_not_borrow_existing_success(self):
        key = self.published()
        for value in (-1, 101, True, 'very bright', None):
            with self.subTest(value=value):
                task = dict(self.task, inputs=dict(self.task['inputs'], value=value))
                result = self.library.assess_task(key, task)
                self.assertEqual(result['status'], 'REJECTED'); self.assertFalse(result['task_success'])

    def test_F13_multiple_incidents_keep_append_only_history(self):
        key = self.published(); points = self.library.inspect(key)['actual_points']
        self.library.quarantine(key, 'VALIDATION_FAILURE', evidence_id=points[0]['evidence_id'])
        self.library.quarantine(key, 'EVIDENCE_DAMAGE', evidence_id=points[1]['evidence_id'])
        out = self.library.inspect(key)
        self.assertEqual(len(out['incidents']), 2); self.assertEqual(out['eligible_points'], [])
        self.assertEqual(self.library.list_knowledge('LOGIC_SIMULATION'), [])

    def test_F14_store_schema_failure_preserves_files(self):
        key = self.draft()['key']
        self.library.db.execute("UPDATE metadata SET value='99' WHERE name='schema'")
        self.library.close()
        from knowledge import KnowledgeLibrary
        self.reject('KNOWLEDGE_SCHEMA_UNSUPPORTED', lambda: KnowledgeLibrary.open(self.root / 'library', approved_roots=[self.root]))
        # Restore only this test's injected metadata to permit normal tearDown.
        import sqlite3
        from contextlib import closing
        with closing(sqlite3.connect(self.root / 'library' / KnowledgeLibrary.FILENAME)) as db, db:
            db.execute('UPDATE metadata SET value=? WHERE name=?', (KnowledgeLibrary.SCHEMA, 'schema'))
        self.library = KnowledgeLibrary.open(self.root / 'library', approved_roots=[self.root])
        self.assertEqual(self.library.inspect(key)['flow_state'], 'DRAFT')

    def test_F15_cost_and_metadata_size_limits(self):
        for item in ({'calls': True, 'reported_usd': '0'}, {'calls': -1, 'reported_usd': '0'},
                     {'calls': 1, 'reported_usd': '-2'}, {'calls': 1, 'reported_usd': 'NaN'}):
            with self.subTest(item=item):
                meta = supplement(); meta['model_cost'] = item
                self.reject('COST_SCHEMA_ERROR', lambda: self.draft(meta))
        meta = supplement(); meta['model_original'] = 'x' * 1048577
        self.reject('KNOWLEDGE_SIZE_LIMIT', lambda: self.draft(meta))

    def test_F16_partially_skipped_flow_does_not_validate_unperformed_setting(self):
        first = dict(self.flow['steps'][0], id='first', argument={'kind': 'literal', 'value': 20})
        self.flow['steps'].insert(0, first)
        key = self.checked(); result, port, plan = self.validation(key)
        self.assertEqual(len(port.calls), 1)
        self.library.record_validation(key, 2, result.evidence)
        out = self.library.inspect(key)
        self.assertFalse(out['actual_points'][0]['setting_trial'])
        authority = __import__('p34deps').records.PublishAuthority(key, 'test.operator', plan.to_dict()['environment_hash'], 'LOGIC_SIMULATION', True)
        self.reject('SETTING_CAPABILITY_NOT_TRIALED', lambda: self.library.publish_logic(key, 3, authority))

    def test_F17_invalid_source_root_configuration_has_no_store_side_effects(self):
        from knowledge import KnowledgeLibrary
        target = self.root / 'invalid-root-config'
        for roots in ([], None, 'anything'):
            with self.subTest(roots=roots):
                self.reject('APPROVED_SOURCE_ROOTS_REQUIRED', lambda: KnowledgeLibrary.create(target, approved_roots=roots))
                self.assertFalse(target.exists())


def load_tests(loader, tests, pattern):
    import unittest
    return unittest.TestSuite(FaultTests(name) for name in dir(FaultTests) if name.startswith('test_F'))
