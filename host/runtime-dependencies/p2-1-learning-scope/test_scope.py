"""Offline P2.1 contract tests. No device, model, or authorization provider."""
import copy
import json
import unittest

from learning_scope import ScopeError, assess_scope, scope_digest, validate_scope


def scope_fixture():
    return {
        'kind': 'LearningScope', 'schema_version': '1.0', 'scope_id': 'learn.example',
        'target': {'app_package': 'edu.sydney.parameterroom', 'app_build': '0.8-parameter-room',
                   'environment_id': 'env.room', 'ui_revision': 'u0', 'domain': 'EXPERIMENT_APP'},
        'task': {'goal': 'Learn to set the bedroom light brightness', 'entity_types': ['light'],
                 'known_start_page': 'parameter_room', 'origin_source_ids': ['src.demo']},
        'allowed_pages': ['parameter_room'], 'modes': ['DEMONSTRATION_ASSISTED'],
        'sources': [{'source_id': 'src.demo', 'mode': 'DEMONSTRATION_ASSISTED',
                     'actor': 'HUMAN_DECLARED', 'channel': 'TEST_FIXTURE',
                     'evidence_ref': 'fixture.demo', 'sha256': 'a' * 64,
                     'origin': {'domain': 'EXPERIMENT_APP', 'app_package': 'edu.sydney.parameterroom',
                                'app_build': '0.8-parameter-room'}}],
        'requested_permissions': {'observe': True, 'navigation': [], 'business_writes': []},
        'authorization_refs': [],
        'budgets': {'max_time_ms': 5000, 'max_observations': 10, 'max_actions': 0,
                    'max_model_requests': 0, 'max_storage_bytes': 65536},
    }


class ScopeContractTests(unittest.TestCase):
    def test_valid_scope_is_detached_and_never_grants_execution(self):
        original = scope_fixture()
        value = validate_scope(original)
        original['task']['goal'] = 'mutated'
        self.assertNotEqual(value['task']['goal'], original['task']['goal'])
        self.assertEqual(len(scope_digest(value)), 64)
        self.assertFalse(assess_scope(value)['execution_authority'])

    def test_combined_modes_retain_each_source(self):
        scope = scope_fixture()
        for mode in ('AUTO_UI', 'DOCUMENT_ASSISTED', 'EXPERT_CORRECTED'):
            scope['modes'].append(mode)
            source = copy.deepcopy(scope['sources'][0])
            source.update(source_id='src.' + mode.lower(), mode=mode, actor='UNKNOWN')
            scope['sources'].append(source)
        self.assertEqual(len(validate_scope(scope)['sources']), 4)

    def test_mode_cannot_hide_human_demonstration(self):
        scope = scope_fixture()
        scope['modes'] = ['AUTO_UI']
        with self.assertRaises(ScopeError):
            validate_scope(scope)

    def test_duplicate_ids_and_unknown_origin_rejected(self):
        for field in ('source_id', 'origin'):
            with self.subTest(field=field):
                scope = scope_fixture()
                if field == 'source_id':
                    scope['sources'].append(copy.deepcopy(scope['sources'][0]))
                else:
                    scope['task']['origin_source_ids'] = ['src.nonexistent']
                with self.assertRaises(ScopeError):
                    validate_scope(scope)

    def test_unknown_task_and_app_fields_produce_gaps_not_invented_values(self):
        scope = scope_fixture()
        scope['task'].update(goal=None, known_start_page=None, entity_types=[])
        scope['target'].update(app_build=None, ui_revision=None)
        scope['allowed_pages'] = []
        value = validate_scope(scope)
        result = assess_scope(value)
        self.assertEqual(result['status'], 'BLOCKED')
        self.assertIn('GAP_TASK_UNCLEAR', result['gaps'])
        self.assertIn('GAP_BUILD_UNKNOWN', result['gaps'])
        self.assertIn('AUDIT_LOCAL_MATERIAL', result['safe_independent_work'])
        self.assertIsNone(value['task']['goal'])

    def test_missing_material_and_forged_authorization_ref_do_not_authorize(self):
        scope = scope_fixture()
        scope['authorization_refs'] = ['approval.please-trust-this']
        result = assess_scope(scope)
        self.assertIn('GAP_MATERIAL_UNAVAILABLE', result['gaps'])
        self.assertIn('GAP_CURRENT_AUTHORIZATION', result['gaps'])
        self.assertFalse(result['execution_authority'])

    def test_invalid_budget_types_and_extra_fields_rejected(self):
        for bad in (-1, True, 1.5, '2', None):
            with self.subTest(bad=bad):
                scope = scope_fixture()
                scope['budgets']['max_actions'] = bad
                with self.assertRaises(ScopeError):
                    validate_scope(scope)
        scope = scope_fixture()
        scope['approved'] = True
        with self.assertRaises(ScopeError):
            validate_scope(scope)

    def test_json_duplicate_field_nonfinite_and_secret_rejected_without_echo(self):
        for raw in ('{"kind":"LearningScope","kind":"LearningScope"}', '{"n":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(ScopeError):
                validate_scope(raw)
        scope = scope_fixture()
        scope['task']['goal'] = 'sk-proj-' + 'fictional-test-value'
        with self.assertRaises(ScopeError) as failure:
            validate_scope(scope)
        self.assertNotIn('fictional-test-value', str(failure.exception))

    def test_no_wildcard_scope_or_android_host_in_business_fields(self):
        for change in ('wildcard', 'host'):
            scope = scope_fixture()
            if change == 'wildcard':
                scope['allowed_pages'] = ['*']
            else:
                scope['requested_permissions']['business_writes'] = [
                    {'host_device_id': 'host.phone', 'property': 'power'}]
            with self.subTest(change=change), self.assertRaises(ScopeError):
                validate_scope(scope)

    def test_empty_sources_remain_declared_missing_not_auto_ui_success(self):
        scope = scope_fixture()
        scope['sources'] = []
        scope['task']['origin_source_ids'] = []
        result = assess_scope(validate_scope(scope))
        self.assertIn('GAP_MATERIAL_UNAVAILABLE', result['gaps'])


if __name__ == '__main__':
    unittest.main()
