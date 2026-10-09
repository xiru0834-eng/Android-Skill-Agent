"""Offline callback/window races; no device or pixel capture."""
import copy
import threading
import time
import unittest

from observation_capture import ObservationCollector, OfflineCapturePort, ScreenshotDelivery
from observation_tree import ObservationError
from p22deps import LearningBudget, ScopeAuthorization, scope_digest
from test_support import scope_fixture, frame_fixture, packet_fixture, Clock, FixturePort


class CaptureTests(unittest.TestCase):
    def setup_collector(self, frames=None, packet=None, **options):
        clock = options.pop('clock', Clock())
        scope = scope_fixture(); port = FixturePort(frames or [frame_fixture(), frame_fixture()], packet, clock)
        auth = ScopeAuthorization(scope_digest(scope), 'env.room', 'fixture.host', 6000, observe=True)
        budget = LearningBudget(scope, clock=clock)
        collector = ObservationCollector(scope, port, authorization=auth, budget=budget, clock=clock, **options)
        return collector, port, clock

    def test_stable_tree_only_has_ids_evidence_and_no_screenshot_call(self):
        c, p, _ = self.setup_collector(); result = c.observe()
        self.assertEqual(result['capture_status'], 'VALID_TREE_ONLY')
        self.assertEqual(result['consistency']['visual_content_check'], 'NOT_EVALUATED')
        self.assertFalse(result['execution_authority']); self.assertEqual(p.screenshot_calls, 0)
        self.assertEqual(len(result['attempts']), 1)
        self.assertNotEqual(result['observation_id'], result['attempts'][0]['capture_attempt_id'])
        self.assertEqual(result['host_device_id'], 'fixture.host')

    def test_each_observation_and_attempt_has_a_unique_id(self):
        c, _, _ = self.setup_collector(); a = c.observe(); b = c.observe()
        self.assertNotEqual(a['observation_id'], b['observation_id'])
        self.assertNotEqual(a['attempts'][0]['capture_attempt_id'], b['attempts'][0]['capture_attempt_id'])

    def test_missing_or_forged_authority_blocks_before_content_reads(self):
        for change in (None, 'native', 'host', 'expired'):
            c, p, _ = self.setup_collector()
            if change is None: c.authorization = None
            else:
                args = {'source': 'CLAIMED_NATIVE_APPROVAL'} if change == 'native' else {
                    'host_device_id': 'other'} if change == 'host' else {'deadline_ms': 1}
                from dataclasses import replace
                c.authorization = replace(c.authorization, **args)
            result = c.observe()
            self.assertEqual(result['capture_status'], 'ENVIRONMENT_ERROR')
            self.assertEqual(p.tree_reads, 0); self.assertEqual(p.screenshot_calls, 0)

    def test_attempts_share_deadline_and_do_not_reuse_old_tree_or_image(self):
        a = frame_fixture(); b = frame_fixture(value=80)
        c, p, _ = self.setup_collector([a, b, b, copy.deepcopy(b)])
        result = c.observe()
        self.assertEqual(result['capture_status'], 'VALID_TREE_ONLY')
        self.assertEqual(len(result['attempts']), 2)
        self.assertEqual(result['attempts'][0]['capture_status'], 'OBSERVATION_INCONSISTENT')
        self.assertEqual(result['tree']['nodes'][-1]['range']['value'], 80)
        self.assertEqual(len(set(p.deadlines)), 1)

    def test_two_inconsistent_attempts_fail_and_preserve_no_valid_payload(self):
        c, _, _ = self.setup_collector([frame_fixture(), frame_fixture(value=80)] * 2)
        result = c.observe()
        self.assertEqual(result['capture_status'], 'OBSERVATION_INCONSISTENT')
        self.assertEqual(len(result['attempts']), 2); self.assertIsNone(result['tree'])

    def test_root_empty_and_stale_have_explicit_failure_or_fresh_retry(self):
        for code in ('ROOT_UNAVAILABLE', 'STALE_NODE_ERROR'):
            c, p, _ = self.setup_collector([ObservationError(code), frame_fixture(), frame_fixture()])
            result = c.observe()
            self.assertEqual(result['capture_status'], 'VALID_TREE_ONLY')
            self.assertEqual(result['attempts'][0]['capture_status'], code)
            self.assertEqual(p.tree_reads, 3)

    def test_optional_unavailable_screenshot_is_explicit_tree_degradation(self):
        c, p, _ = self.setup_collector(packet=packet_fixture(status='UNAVAILABLE'))
        result = c.observe(screenshot='OPTIONAL')
        self.assertEqual(result['capture_status'], 'PARTIAL_SCREENSHOT_FAILED')
        self.assertEqual(result['screenshot']['status'], 'UNAVAILABLE')
        self.assertEqual(result['consistency']['visual_content_check'], 'NOT_EVALUATED')
        self.assertEqual(p.released, 1)

    def test_required_screenshot_failure_is_not_valid_observation(self):
        c, p, _ = self.setup_collector(packet=packet_fixture(status='FAILED'))
        result = c.observe(screenshot='REQUIRED')
        self.assertEqual(result['capture_status'], 'SCREENSHOT_FAILED'); self.assertIsNone(result['tree'])
        self.assertEqual(p.released, 1)

    def test_window_time_check_is_not_content_check(self):
        c, p, _ = self.setup_collector(packet=packet_fixture())
        result = c.observe(screenshot='OPTIONAL')
        self.assertEqual(result['consistency']['pairing_status'], 'WINDOW_TIME_CHECKED')
        self.assertEqual(result['consistency']['visual_content_check'], 'NOT_EVALUATED')
        self.assertEqual(result['capture_status'], 'VALID_WINDOW_TIME_CHECKED')
        self.assertEqual(p.released, 1)

    def test_old_or_wrong_request_window_host_and_timestamp_cannot_pair(self):
        for changes in ({'request_id': 'old'}, {'window_id': 9}, {'host_device_id': 'other'},
                        {'captured_uptime_ms': 0}, {'clock_domain': 'elapsedRealtime'}):
            c, p, _ = self.setup_collector(packet=packet_fixture(**changes))
            result = c.observe(screenshot='OPTIONAL')
            self.assertNotIn(result['capture_status'], ('VALID_WINDOW_TIME_CHECKED', 'PARTIAL_SCREENSHOT_FAILED'))
            self.assertIsNone(result['tree']); self.assertGreaterEqual(p.released, 1)

    def test_simulated_visual_conflict_is_rejected_not_real_vision_proof(self):
        packet = packet_fixture(content_check={'source': 'OFFLINE_SIMULATED_VISUAL_CHECK',
                                'facts': [{'node_local_id': '0.1', 'field': 'range.value', 'value': 80}]})
        c, _, _ = self.setup_collector(packet=packet)
        result = c.observe(screenshot='OPTIONAL')
        self.assertEqual(result['capture_status'], 'OBSERVATION_INCONSISTENT')

    def test_nav_tab_popup_entity_and_visible_slice_changes_are_not_paired(self):
        for field, change in [('tab', 'other'), ('popup', 'dialog'), ('expanded', ['panel']), ('visible_slice', 'bottom')]:
            b = frame_fixture(); b['navigation_context'][field] = change
            c, _, _ = self.setup_collector([frame_fixture(), b] * 2)
            self.assertEqual(c.observe()['capture_status'], 'OBSERVATION_INCONSISTENT')

    def test_external_sensitive_window_blocked_without_copying_external_text(self):
        b = frame_fixture(); b['window']['sensitive'] = True
        c, p, _ = self.setup_collector([b, b])
        result = c.observe(screenshot='OPTIONAL')
        self.assertEqual(result['capture_status'], 'BLOCKED_BY_OVERLAY')
        self.assertEqual(p.tree_reads, 0); self.assertEqual(p.screenshot_calls, 0)

    def test_same_app_popup_is_context_but_foreign_overlay_blocks(self):
        a = frame_fixture(); a['navigation_context']['popup'] = 'same-app-dialog'
        c, _, _ = self.setup_collector([a, copy.deepcopy(a)])
        self.assertEqual(c.observe()['capture_status'], 'VALID_TREE_ONLY')
        a['window']['covered'] = True
        c, p, _ = self.setup_collector([a, a])
        self.assertEqual(c.observe()['capture_status'], 'BLOCKED_BY_OVERLAY'); self.assertEqual(p.tree_reads, 0)

    def test_cancel_before_and_during_capture_prevents_new_reads(self):
        c, p, _ = self.setup_collector(); c.cancel()
        self.assertEqual(c.observe()['capture_status'], 'CANCELLED'); self.assertEqual(p.tree_reads, 0)
        c, p, _ = self.setup_collector(); p.after_first_read = c.cancel
        self.assertEqual(c.observe()['capture_status'], 'CANCELLED'); self.assertEqual(p.tree_reads, 1)

    def test_timeout_backward_clock_and_suspend_are_not_current_facts(self):
        c, p, clock = self.setup_collector(); p.after_first_read = lambda: clock.advance(2100)
        self.assertEqual(c.observe()['capture_status'], 'OBSERVATION_TIMEOUT'); self.assertEqual(p.tree_reads, 1)
        b = frame_fixture(); b['uptime_end_ms'] = 0
        c, _, _ = self.setup_collector([frame_fixture(), b])
        self.assertEqual(c.observe()['capture_status'], 'CLOCK_DOMAIN_ERROR')
        b = frame_fixture(); b['elapsed_end_ms'] += 100
        c, _, _ = self.setup_collector([frame_fixture(), b])
        self.assertEqual(c.observe()['capture_status'], 'CLOCK_DOMAIN_ERROR')

    def test_late_callback_after_timeout_released_and_cannot_revive_observation(self):
        c, p, clock = self.setup_collector()
        p.late_screenshot = True
        result = c.observe(screenshot='REQUIRED', total_budget_ms=30)
        self.assertEqual(result['capture_status'], 'OBSERVATION_TIMEOUT')
        p.deliver_late(); self.assertEqual(p.released, 1); self.assertIsNone(result['tree'])

    def test_claimed_real_android_port_does_not_silently_become_native_evidence(self):
        c, p, _ = self.setup_collector(); p.channel = 'REAL_ANDROID'
        self.assertEqual(c.observe()['capture_status'], 'NATIVE_INTEGRATION_UNAVAILABLE')
        self.assertEqual(p.tree_reads, 0)

    def test_tree_timestamp_before_current_request_is_rejected(self):
        stale = frame_fixture(); stale['elapsed_start_ms'] = 900; stale['elapsed_end_ms'] = 920
        c, _, _ = self.setup_collector([stale, copy.deepcopy(stale)])
        self.assertEqual(c.observe()['capture_status'], 'CLOCK_DOMAIN_ERROR')

    def test_screenshot_diagnostic_cannot_persist_credentials_or_unknown_fields(self):
        c, _, _ = self.setup_collector(packet=packet_fixture(status='FAILED', error_code='sk-proj-' + 'X'*30))
        result = c.observe(screenshot='OPTIONAL')
        self.assertEqual(result['capture_status'], 'INVALID_SCREENSHOT')
        self.assertNotIn('sk-proj-', str(result))

    def test_release_error_is_explicit_and_not_a_valid_observation(self):
        c, p, _ = self.setup_collector(packet=packet_fixture())
        original = p.request_screenshot
        def fail_release(request, deadline, callback):
            def replace_delivery(delivery):
                delivery.release = lambda: (_ for _ in ()).throw(RuntimeError('release failure'))
                callback(delivery)
            return original(request, deadline, replace_delivery)
        p.request_screenshot = fail_release
        self.assertEqual(c.observe(screenshot='OPTIONAL')['capture_status'], 'CAPTURE_RESOURCE_ERROR')

    def test_screenshot_ids_have_strict_types_not_bool_int_equality(self):
        c, _, _ = self.setup_collector(packet=packet_fixture(window_id=True))
        self.assertEqual(c.observe(screenshot='OPTIONAL')['capture_status'], 'INVALID_SCREENSHOT')

    def test_mutated_scope_invalidates_future_content_reads(self):
        c, p, _ = self.setup_collector()
        p.after_first_read = lambda: c.scope['task']['entity_types'].append('light')
        self.assertEqual(c.observe()['capture_status'], 'ENVIRONMENT_ERROR')
        self.assertEqual(p.tree_reads, 1)

    def test_callback_time_in_future_does_not_create_valid_observation(self):
        c, _, _ = self.setup_collector(packet=packet_fixture(callback_elapsed_ms=2500))
        self.assertEqual(c.observe(screenshot='OPTIONAL')['capture_status'], 'CLOCK_DOMAIN_ERROR')


if __name__ == '__main__': unittest.main()
