from contextlib import closing
import copy
import sqlite3
import tempfile
import unittest
from pathlib import Path

from learning_ledger import LearningLedger
from learning_scope import (MaterialReceipt, ReadinessContext, ScopeAuthorization,
                            ScopeError, assess_scope, scope_digest, validate_scope)
from test_ledger import cost_event
from test_scope import scope_fixture


class ReviewTests(unittest.TestCase):
    def test_missing_second_human_source_cannot_claim_complete_demo_count(self):
        scope = scope_fixture()
        extra = copy.deepcopy(scope['sources'][0])
        extra['source_id'] = 'src.demo2'
        scope['sources'].append(extra)
        with tempfile.TemporaryDirectory(prefix='p21-review-') as temporary:
            store = LearningLedger.create(Path(temporary) / 'store.sqlite3', scope)
            store.append(cost_event(), expected_revision=0)
            self.assertIsNone(store.inspect()['human_cost']['DEMONSTRATION']['total'])

    def test_unmeasured_automated_cost_is_not_reported_as_zero(self):
        scope = scope_fixture()
        scope['sources'][0]['actor'] = 'AUTOMATED'
        with tempfile.TemporaryDirectory(prefix='p21-review-') as temporary:
            store = LearningLedger.create(Path(temporary) / 'store.sqlite3', scope)
            store.append(cost_event(actor='AUTOMATED', amount=None), expected_revision=0)
            self.assertIsNone(store.inspect()['automated_cost']['DEMONSTRATION']['total'])

    def test_deleted_tail_event_is_detected_even_with_remaining_valid_hashes(self):
        with tempfile.TemporaryDirectory(prefix='p21-review-') as temporary:
            path = Path(temporary) / 'store.sqlite3'
            store = LearningLedger.create(path, scope_fixture())
            store.append(cost_event(), expected_revision=0)
            with closing(sqlite3.connect(path)) as connection, connection:
                connection.execute('DELETE FROM events')
            with self.assertRaises(ScopeError):
                store.inspect()

    def test_source_target_domain_keeps_experiment_out_of_teacher_evidence(self):
        scope = scope_fixture()
        scope['target']['domain'] = 'TEACHER_APP'
        result = assess_scope(scope)
        self.assertIn('GAP_SOURCE_DOMAIN_MISMATCH', result['gaps'])

    def test_source_app_mismatch_is_recorded_not_silently_reused(self):
        scope = scope_fixture()
        scope['sources'][0]['origin']['app_package'] = 'other.app'
        result = assess_scope(scope)
        self.assertIn('GAP_SOURCE_APP_MISMATCH', result['gaps'])

    def test_current_ui_requires_matching_build_and_history_stays_history(self):
        scope = scope_fixture()
        scope['sources'][0].update(channel='CURRENT_UI', mode='AUTO_UI', actor='AUTOMATED')
        scope['modes'] = ['AUTO_UI']
        scope['sources'][0]['origin']['app_build'] = 'old-version'
        self.assertIn('GAP_CURRENT_UI_BUILD_MISMATCH', assess_scope(scope)['gaps'])

    def test_current_authority_is_hash_environment_time_and_scope_bound(self):
        scope = scope_fixture()
        receipts = (MaterialReceipt('src.demo', 'a' * 64, 'EXPERIMENT_APP'),)
        authorization = ScopeAuthorization(scope_digest(scope), 'env.room', 'host.fixture', 5000, observe=True)
        context = ReadinessContext(True, '0.8-parameter-room', 'env.room', 'u0', receipts, authorization, True)
        result = assess_scope(scope, context, now_ms=1000)
        self.assertEqual(result['status'], 'OFFLINE_PREREQUISITES_CHECKED')
        self.assertFalse(result['execution_authority'])
        for change, expected in (({'scope_hash': 'b' * 64}, 'GAP_CURRENT_AUTHORIZATION'),
                                 ({'environment_id': 'wrong'}, 'GAP_CURRENT_AUTHORIZATION'),
                                 ({'deadline_ms': 1000}, 'GAP_CURRENT_AUTHORIZATION'),
                                 ({'observe': False}, 'GAP_AUTHORIZATION_SCOPE'),
                                 ({'source': 'CLAIMED_NATIVE_APPROVAL'}, 'GAP_CURRENT_AUTHORIZATION')):
            from dataclasses import replace
            altered = replace(context, authorization=replace(authorization, **change))
            with self.subTest(change=change):
                self.assertIn(expected, assess_scope(scope, altered, now_ms=1000)['gaps'])

    def test_formal_gate_and_material_digest_fail_independently(self):
        from dataclasses import replace
        scope = scope_fixture()
        authorization = ScopeAuthorization(scope_digest(scope), 'env.room', 'host.fixture', 5000, observe=True)
        context = ReadinessContext(True, '0.8-parameter-room', 'env.room', 'u0',
                                   (MaterialReceipt('src.demo', 'b' * 64, 'EXPERIMENT_APP'),), authorization, False)
        result = assess_scope(scope, context, now_ms=1000)
        self.assertIn('GAP_MATERIAL_UNAVAILABLE', result['gaps'])
        self.assertIn('GAP_ORIGINAL_FORMAL_GATE', result['gaps'])
        self.assertNotIn('GAP_CURRENT_AUTHORIZATION', result['gaps'])

    def test_budget_envelope_and_bad_json_object_bounded(self):
        for value in (1 << 3000, float('inf')):
            scope = scope_fixture()
            scope['budgets']['max_time_ms'] = value
            with self.subTest(value=type(value).__name__), self.assertRaises(ScopeError):
                validate_scope(scope)
        cycle = {}
        cycle['cycle'] = cycle
        with self.assertRaises(ScopeError):
            validate_scope(cycle)

    def test_task_origin_not_supplied_is_a_gap(self):
        scope = scope_fixture()
        scope['task']['origin_source_ids'] = []
        self.assertIn('GAP_TASK_ORIGIN_MISSING', assess_scope(scope)['gaps'])

    def test_malformed_current_context_is_rejected_not_an_unhandled_type_error(self):
        scope = scope_fixture()
        auth = ScopeAuthorization(scope_digest(scope), 'env.room', 'host.fixture', 5000,
                                  observe=True, business_writes=(['entity', 'power'],))
        context = ReadinessContext(authorization=auth)
        with self.assertRaises(ScopeError):
            assess_scope(scope, context, now_ms=1000)

    def test_real_model_metadata_is_not_model_execution_proof(self):
        with tempfile.TemporaryDirectory(prefix='p21-generation-') as temporary:
            store = LearningLedger.create(Path(temporary) / 'store.sqlite3', scope_fixture())
            store.append({'kind': 'GENERATION', 'event_id': 'gen.declared', 'source_ids': ['src.demo'],
                          'channel': 'REAL_MODEL', 'output_sha256': 'a' * 64,
                          'evidence_ref': 'declared.not-executed'}, expected_revision=0)
            self.assertEqual(store.inspect()['generation_evidence'], 'DECLARED_METADATA_NOT_MODEL_CALL_PROOF')


if __name__ == '__main__':
    unittest.main()
