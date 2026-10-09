import unittest
from copy import deepcopy
from fixtures import original_bundle
from environment import audited_room_profile, EnvironmentProfile
from fixtures import bundle
from compiler import compile_flow, CompileError


class StaticCompilerTests(unittest.TestCase):
    def rejected(self, data, code, path=None, environment=None):
        with self.assertRaises(CompileError) as caught:
            compile_flow(*data, environment)
        self.assertEqual(caught.exception.code, code)
        if path:
            self.assertEqual(caught.exception.path, path)

    def test_G1_compile_brightness_old_wire(self):
        result = compile_flow(*bundle(), None)
        self.assertEqual(result.to_dict()['steps'][0]['call'],
                         {'skill': 'SetBrightness', 'args': {'device': 'bedroom_light', 'percent': 80}})

    def test_G1_temperature_uses_celsius(self):
        result = compile_flow(*bundle('SetTemperature', 26), None)
        self.assertEqual(result.to_dict()['steps'][0]['call']['args']['celsius'], 26)

    def test_G2_entity_actual_temperature_domain(self):
        with self.assertRaises(CompileError) as caught:
            compile_flow(*bundle('SetTemperature', 31), None)
        self.assertEqual((caught.exception.code, caught.exception.path),
                         ('ENTITY_DOMAIN_ERROR', '$.steps[0].argument'))

    def test_G2_precise_parameter_error_path(self):
        flow, package, task = bundle()
        task['inputs']['value'] = 80.0
        with self.assertRaises(CompileError) as caught:
            compile_flow(flow, package, task, None)
        self.assertEqual(caught.exception.path, '$.task.inputs.value')

    def test_G1_four_actual_combinations(self):
        for skill, entity, value in [('SetPower', 'bedroom_light', 'on'), ('SetPower', 'bedroom_ac', 'off'),
                                     ('SetBrightness', 'bedroom_light', 100), ('SetTemperature', 'bedroom_ac', 16)]:
            with self.subTest(skill=skill, entity=entity):
                flow, package, task = bundle(skill, value)
                task['inputs']['entity']['entity_id'] = entity
                result = compile_flow(flow, package, task, None).to_dict()
                self.assertEqual(result['steps'][0]['call']['args']['device'], entity)
                self.assertFalse(result['execution_authority'])

    def test_G1_original_read_assert_contract_compiles_with_blocker(self):
        result = compile_flow(*original_bundle(), None).to_dict()
        self.assertEqual([s['op'] for s in result['steps']], ['READ', 'ASSERT', 'CALL', 'ASSERT'])
        self.assertIn('unknown.read_adapter', result['blocking_unknowns'])
        self.assertFalse(result['ready_for_device_execution'])

    def test_G3_ABA_order_and_no_collapsing(self):
        flow, package, task = bundle()
        flow['steps'] = [dict(id='set_' + str(i), op='call', capability='SetBrightness',
                             entity_input='entity', argument={'kind': 'literal', 'value': value})
                         for i, value in enumerate([20, 80, 20])]
        task['inputs']['value'] = 20
        result = compile_flow(flow, package, task, None).to_dict()
        self.assertEqual([s['call']['args']['percent'] for s in result['steps']], [20, 80, 20])
        self.assertEqual(result['call_count'], 3)

    def test_G3_ordered_read_reference_is_not_current_state(self):
        flow, package, task = bundle()
        flow['steps'].insert(0, dict(id='before', op='read', target=flow['allowed_effects'][0]))
        flow['steps'][1]['argument'] = {'kind': 'read', 'step_id': 'before'}
        result = compile_flow(flow, package, task, None).to_dict()
        self.assertEqual(result['steps'][1]['value']['kind'], 'read')
        self.assertIsNone(result['steps'][1]['call'])

    def test_G3_forward_read_localized(self):
        flow, package, task = bundle()
        flow['steps'][0]['argument'] = {'kind': 'read', 'step_id': 'later'}
        flow['steps'].append(dict(id='later', op='read', target=flow['allowed_effects'][0]))
        self.rejected((flow, package, task), 'BAD_REFERENCE', '$.steps[0].argument')

    def test_G2_global_range_types_and_missing_values(self):
        for value in (-1, 101, True, 80.0, None, '80'):
            with self.subTest(value=value):
                self.rejected(bundle(value=value), 'CONSTRAINT_ERROR' if type(value) is int else 'TYPE_MISMATCH')
        flow, package, task = bundle()
        del task['inputs']['value']
        self.rejected((flow, package, task), 'BAD_REFERENCE', '$.task.inputs')

    def test_G2_wrong_unit(self):
        flow, package, task = bundle()
        flow['inputs'][1]['unit'] = 'kelvin'
        self.rejected((flow, package, task), 'TYPE_MISMATCH', '$.steps[0].argument')

    def test_G2_entity_and_host_are_separate(self):
        flow, package, task = bundle()
        task['inputs']['entity']['entity_id'] = 'host.test_fixture'
        self.rejected((flow, package, task), 'TYPE_MISMATCH')
        task['host_device_id'] = 'bedroom_light'
        task['inputs']['entity']['entity_id'] = 'bedroom_light'
        self.rejected((flow, package, task), 'ENTITY_HOST_CONFUSION')

    def test_G2_discrete_domain_step_not_rounded(self):
        for domain, value in [({'values': [20, 40, 60]}, 80), ({'min': 0, 'max': 100, 'step': 2}, 81)]:
            with self.subTest(domain=domain):
                env = audited_room_profile().to_dict()
                env['targets']['bedroom_light.brightnessPercent']['domain'] = domain
                self.rejected(bundle(value=value), 'ENTITY_DOMAIN_ERROR', '$.steps[0].argument', EnvironmentProfile.test_fixture(env))

    def test_G3_unknown_capability_and_unsupported_syntax(self):
        flow, package, task = bundle()
        flow['steps'][0]['capability'] = 'PublishConfig'
        self.rejected((flow, package, task), 'UNKNOWN_CAPABILITY')
        for op in ('if', 'while', 'eval', 'python', 'shell'):
            with self.subTest(op=op):
                data = bundle()
                data[0]['steps'][0]['op'] = op
                self.rejected(data, 'UNSUPPORTED_STEP')

    def test_G3_all_static_steps_checked_not_masked_by_false_condition(self):
        flow, package, task = bundle()
        flow['preconditions'] = [{'op': 'equals', 'left': {'kind': 'literal', 'value': 1},
                                 'right': {'kind': 'literal', 'value': 2}}]
        flow['steps'].append(dict(id='bad', op='call', capability='SetBrightness', entity_input='entity',
                                 argument={'kind': 'literal', 'value': 101}))
        self.rejected((flow, package, task), 'CONSTRAINT_ERROR', '$.steps[1].argument')

    def test_G3_dependency_and_call_limit(self):
        for count in (31, 32, 33):
            with self.subTest(count=count):
                flow, package, task = bundle()
                flow['steps'] = [dict(flow['steps'][0], id='set_' + str(i)) for i in range(count)]
                if count == 33:
                    self.rejected((flow, package, task), 'CALL_LIMIT')
                else:
                    self.assertEqual(compile_flow(flow, package, task, None).to_dict()['call_count'], count)
        data = bundle()
        data[0]['dependencies']['registry_sha256'] = '0' * 64
        self.rejected(data, 'DEPENDENCY_MISMATCH')

    def test_G3_duplicate_steps_and_write_preserve_conflict(self):
        data = bundle()
        data[0]['steps'].append(deepcopy(data[0]['steps'][0]))
        self.rejected(data, 'DUPLICATE_ID')
        data = bundle()
        data[0]['must_preserve'] = deepcopy(data[0]['allowed_effects'])
        self.rejected(data, 'CONTRACT_CONFLICT')

    def test_GD_defined_is_not_gui_implemented(self):
        for skill, value in [('SetFanSpeed', 2), ('SetCurtain', 40), ('SetMode', 'auto'),
                             ('SetTargetHumidity', 50), ('SetColorTemperature', 3000)]:
            with self.subTest(skill=skill):
                self.rejected(bundle(skill, value), 'UNSUPPORTED_CAPABILITY')

    def test_GD_real_controller_reader_verifier_and_environment(self):
        for field, value, code in [('implemented', False, 'UNSUPPORTED_CAPABILITY'),
                                   ('controller', 'SET_TEXT', 'UNSUPPORTED_CONTROLLER'),
                                   ('reader', '', 'VERIFIER_UNAVAILABLE'),
                                   ('verifier', '', 'VERIFIER_UNAVAILABLE'),
                                   ('submission', 'UNKNOWN', 'UNKNOWN_SUBMISSION_SEMANTICS'),
                                   ('submission', 'BUSINESS_PUBLISH', 'UNSUPPORTED_BUSINESS_SUBMISSION')]:
            with self.subTest(field=field):
                env = audited_room_profile().to_dict()
                env['targets']['bedroom_light.brightnessPercent'][field] = value
                self.rejected(bundle(), code, environment=EnvironmentProfile.test_fixture(env))
        data = bundle()
        data[1]['environment']['app_version'] = 'changed'
        self.rejected(data, 'ENVIRONMENT_MISMATCH')

    def test_G7_plan_is_copy_and_has_no_model_code_or_geometry(self):
        flow, package, task = bundle()
        result = compile_flow(flow, package, task, None)
        first = result.to_dict()
        first['steps'][0]['call']['args']['percent'] = 1
        task['inputs']['value'] = 10
        self.assertEqual(result.to_dict()['steps'][0]['call']['args']['percent'], 80)
        self.assertNotIn('bounds', result._json)

    def test_G3_static_contradictory_goal_stops_before_steps(self):
        flow, package, task = bundle()
        flow['steps'][0]['argument'] = {'kind': 'literal', 'value': 20}
        self.rejected((flow, package, task), 'CONTRACT_CONFLICT', '$.goals[0]')

    def test_G5_controller_input_commit_requires_evidence(self):
        env = audited_room_profile().to_dict()
        target = env['targets']['bedroom_light.brightnessPercent']
        target['submission'] = 'CONTROLLER_INPUT_COMMIT'
        self.rejected(bundle(), 'SUBMISSION_EVIDENCE_REQUIRED', environment=EnvironmentProfile.test_fixture(env))
        target['commit_evidence_verified'] = True
        result = compile_flow(*bundle(), EnvironmentProfile.test_fixture(env)).to_dict()
        self.assertEqual(result['steps'][0]['submission'], 'CONTROLLER_INPUT_COMMIT')
        self.assertEqual(result['call_count'], 1)  # No invented business Publish/Save call.

    def test_G2_invalid_trusted_domain_cannot_crash_or_round(self):
        for domain in [{'min': 0, 'max': 100, 'step': 0}, {'min': 0, 'max': 99, 'step': 2},
                       {'values': [True, False]}, {'values': [20, 20]}]:
            with self.subTest(domain=domain):
                env = audited_room_profile().to_dict()
                env['targets']['bedroom_light.brightnessPercent']['domain'] = domain
                self.rejected(bundle(), 'ENVIRONMENT_DOMAIN_INVALID', environment=EnvironmentProfile.test_fixture(env))


if __name__ == '__main__':
    unittest.main()
