"""Boundary validation of serialized evidence; not native authorization."""
import copy
import unittest

from observation_contract import validate_observation
from observation_identity import derive_page
from observation_tree import ObservationError
from test_identity import observation


class ContractTests(unittest.TestCase):
    def test_detached_valid_wire_does_not_retain_mutable_input(self):
        obs = observation(); detached = validate_observation(obs)
        obs['tree']['nodes'][0]['text'] = 'changed'
        self.assertNotEqual(detached['tree']['nodes'][0]['text'], 'changed')

    def test_window_guard_cannot_be_forged_in_saved_observation(self):
        for field, value in [('covered', True), ('sensitive', True), ('active', False), ('window_id', True)]:
            obs = observation(); obs['window_before'][field] = obs['window_after'][field] = value
            with self.subTest(field=field), self.assertRaises(ObservationError): validate_observation(obs)

    def test_nested_node_permit_or_wrong_digest_is_rejected_by_identity_too(self):
        for field, value in [('input_permit', {'approved': True}), ('text', 'forged text')]:
            obs = observation(); obs['tree']['nodes'][-1][field] = value
            with self.subTest(field=field), self.assertRaises(ObservationError): derive_page(obs, entity_types=['room'])

    def test_unknown_navigation_attempt_and_budget_fields_cannot_survive_contract(self):
        for field in ('navigation_context', 'attempts', 'budget'):
            obs = observation()
            target = obs[field][0] if field == 'attempts' else obs[field]
            target['action_permit'] = {'approved': True}
            with self.subTest(field=field), self.assertRaises(ObservationError): validate_observation(obs)

    def test_false_source_and_legacy_flat_trace_do_not_become_observation(self):
        values = [{'kind':'Trace','events':[]}, {'kind':'PageObservation','tree':[]}]
        obs = observation(); obs['channel'] = 'REAL_ANDROID'; values.append(obs)
        for value in values:
            with self.subTest(kind=value.get('kind')), self.assertRaises(ObservationError): validate_observation(value)

    def test_failed_record_cannot_keep_valid_tree_or_screenshot(self):
        obs = observation(); obs['capture_status'] = 'OBSERVATION_INCONSISTENT'
        with self.assertRaises(ObservationError): validate_observation(obs)

    def test_wrong_timeline_attempt_id_and_environment_schema_are_explicit(self):
        mutations = [('started_elapsed_ms', 5000), ('observation_id','../unsafe'), ('known_scope','COMPLETE_APP_MAP')]
        for field, value in mutations:
            obs = observation(); obs[field] = value
            with self.subTest(field=field), self.assertRaises(ObservationError): validate_observation(obs)

    def test_malformed_nested_json_uses_contract_errors_not_python_crashes(self):
        base = observation(); failures = []; checked = 0
        def paths(value, path=()):
            if type(value) is dict:
                for key, item in value.items():
                    yield path+(key,)
                    yield from paths(item,path+(key,))
            elif type(value) is list:
                for i,item in enumerate(value[:2]): yield from paths(item,path+(i,))
        for path in paths(base):
            for replacement in (None,True,[],{},'invalid',-1):
                changed = copy.deepcopy(base); cursor = changed
                for part in path[:-1]: cursor = cursor[part]
                cursor[path[-1]] = replacement; checked += 1
                try: validate_observation(changed)
                except ObservationError: pass
                except Exception as error: failures.append({'path':str(path),'error':type(error).__name__})
        self.assertGreater(checked,500)
        self.assertEqual(failures,[],str(failures[:10]))

    def test_attempt_digest_cannot_disagree_with_published_tree(self):
        obs = observation(); obs['attempts'][-1]['tree_b_digest'] = '0'*64
        with self.assertRaises(ObservationError): validate_observation(obs)

    def test_content_checked_status_requires_actual_simulated_content_evidence(self):
        from test_capture import CaptureTests
        from test_support import packet_fixture
        c,_,_ = CaptureTests().setup_collector(packet=packet_fixture())
        obs = c.observe(screenshot='OPTIONAL')
        obs['capture_status'] = obs['attempts'][-1]['capture_status'] = 'VALID_CONTENT_CHECKED_SIMULATED'
        obs['consistency']['pairing_status'] = 'CONTENT_CHECKED_SIMULATED'
        obs['consistency']['visual_content_check'] = 'SIMULATED_NOT_MODEL'
        with self.assertRaises(ObservationError): validate_observation(obs)


if __name__ == '__main__': unittest.main()
