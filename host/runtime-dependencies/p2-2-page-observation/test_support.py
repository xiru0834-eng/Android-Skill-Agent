"""Only explicit synthetic fixtures. No oracle is imported into implementation."""
import copy
from observation_tree import ObservationError
from p22deps import validate_scope
from test_tree import raw_node, raw_tree


def scope_fixture():
    return validate_scope({
        'kind': 'LearningScope', 'schema_version': '1.0', 'scope_id': 'learn.fixture',
        'target': {'app_package': 'edu.sydney.parameterroom', 'app_build': '0.8-parameter-room',
                   'environment_id': 'env.room', 'ui_revision': 'u0', 'domain': 'EXPERIMENT_APP'},
        'task': {'goal': 'Observe the current page', 'entity_types': ['room'],
                 'known_start_page': 'parameter_room', 'origin_source_ids': ['src.fixture']},
        'allowed_pages': ['parameter_room'], 'modes': ['AUTO_UI'],
        'sources': [{'source_id': 'src.fixture', 'mode': 'AUTO_UI', 'actor': 'AUTOMATED',
                     'channel': 'TEST_FIXTURE', 'evidence_ref': 'fixture:scope', 'sha256': 'a' * 64,
                     'origin': {'domain': 'EXPERIMENT_APP', 'app_package': 'edu.sydney.parameterroom', 'app_build': '0.8-parameter-room'}}],
        'requested_permissions': {'observe': True, 'navigation': [], 'business_writes': []}, 'authorization_refs': [],
        'budgets': {'max_time_ms': 5000, 'max_observations': 20, 'max_actions': 0,
                    'max_model_requests': 0, 'max_storage_bytes': 1048576}})


def frame_fixture(value=20, entity='Room 101', **changes):
    frame = {'environment': scope_fixture()['target'], 'host_device_id': 'fixture.host',
             'boot_session_id': 'fixture.boot', 'observer_session_id': 'fixture.observer',
             'window': {'package': 'edu.sydney.parameterroom', 'window_id': 1, 'display_id': 0,
                        'type': 'APPLICATION', 'focused': True, 'active': True, 'layer': 0,
                        'covered': False, 'sensitive': False},
             'elapsed_start_ms': 1000, 'elapsed_end_ms': 1020,
             'uptime_start_ms': 500, 'uptime_end_ms': 520,
             'navigation_context': {'tab': None, 'popup': None, 'expanded': [],
                                    'entry': None, 'visible_slice': 'top', 'page_hint': 'parameter_room'},
             'tree': raw_tree([raw_node(), raw_node('0.0', '0', heading=True, text=entity, role='heading',
                                                   class_name='android.widget.TextView'),
                               raw_node('0.1', '0', role='slider', class_name='android.widget.SeekBar',
                                        resource_id='app:id/value', range={'min': 0, 'max': 100, 'value': value, 'kind': 'int'})])}
    frame.update(changes); return frame


def packet_fixture(**changes):
    packet = {'request_id': None, 'status': 'AVAILABLE', 'window_id': 1, 'display_id': 0,
              'host_device_id': 'fixture.host', 'boot_session_id': 'fixture.boot',
              'clock_domain': 'uptimeMillis', 'captured_uptime_ms': 520,
              'callback_elapsed_ms': 1020, 'evidence_ref': 'fixture:screenshot-metadata-only',
              'sha256': 'b' * 64, 'dimensions': [100, 100], 'error_code': None,
              'content_check': None}
    packet.update(changes); return packet


class Clock:
    def __init__(self): self.now = 1000
    def __call__(self): return self.now
    def advance(self, ms): self.now += ms


class FixturePort:
    channel = 'OFFLINE_CALLBACK_SIMULATION'
    def __init__(self, frames, packet, clock):
        self.frames = frames; self.packet = packet; self.clock = clock; self.position = 0
        self.tree_reads = self.screenshot_calls = self.released = 0
        self.deadlines = []; self.after_first_read = None; self.late_screenshot = False; self.pending = None

    def guard(self):
        frame = self.frames[min(self.position, len(self.frames)-1)]
        if isinstance(frame, Exception): frame = frame_fixture()
        return {k: copy.deepcopy(v) for k, v in frame.items() if k not in {'tree', 'navigation_context',
                'elapsed_start_ms', 'elapsed_end_ms', 'uptime_start_ms', 'uptime_end_ms'}}

    def read_frame(self, deadline_ms, attempt_id):
        self.tree_reads += 1; self.deadlines.append(deadline_ms)
        frame = self.frames[min(self.position, len(self.frames)-1)]; self.position += 1
        if self.tree_reads == 1 and self.after_first_read: self.after_first_read()
        if isinstance(frame, Exception): raise frame
        result = copy.deepcopy(frame)
        delta = (self.position - 1) * 20
        for key in ('elapsed_start_ms', 'elapsed_end_ms', 'uptime_start_ms', 'uptime_end_ms'):
            result[key] += delta
        self.clock.now = max(self.clock.now, result['elapsed_end_ms'])
        return result

    def request_screenshot(self, request_id, deadline_ms, callback):
        self.screenshot_calls += 1; self.deadlines.append(deadline_ms)
        packet = copy.deepcopy(self.packet or packet_fixture(status='UNAVAILABLE'))
        if packet['request_id'] is None: packet['request_id'] = request_id
        # Each new fixture request has fresh capture/callback times. Deliberately
        # malformed values remain unchanged for stale/time-domain tests.
        if packet['callback_elapsed_ms'] == 1020: packet['callback_elapsed_ms'] = self.clock.now
        if packet['captured_uptime_ms'] == 520: packet['captured_uptime_ms'] = self.clock.now - 500
        from observation_capture import ScreenshotDelivery
        delivery = ScreenshotDelivery(packet, lambda: setattr(self, 'released', self.released+1))
        if self.late_screenshot: self.pending = (callback, delivery)
        else: callback(delivery)

    def deliver_late(self):
        callback, delivery = self.pending; callback(delivery)
