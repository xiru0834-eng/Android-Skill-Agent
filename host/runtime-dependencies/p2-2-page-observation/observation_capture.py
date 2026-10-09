"""Bounded offline capture orchestration. Not a native approval issuer or device tool."""
from dataclasses import dataclass, field
import threading
import time
import uuid

from observation_tree import ObservationError, copy_tree, identifier, plain_copy, require
from p22deps import LearningBudget, ScopeAuthorization, ScopeError, scope_digest, validate_scope

TOTAL_MS, PAIR_MS, MAX_ATTEMPTS = 2000, 250, 2
RETRYABLE = {'OBSERVATION_INCONSISTENT', 'ROOT_UNAVAILABLE', 'STALE_NODE_ERROR'}
VALID = {'VALID_TREE_ONLY', 'VALID_WINDOW_TIME_CHECKED', 'VALID_CONTENT_CHECKED_SIMULATED', 'PARTIAL_SCREENSHOT_FAILED'}


class OfflineCapturePort:
    """Structural boundary: guard/read_frame/request_screenshot, no input methods.

    Only OFFLINE_CALLBACK_SIMULATION is accepted in this implementation.
    Real native approval + service transport are intentionally unavailable.
    """
    channel = 'OFFLINE_CALLBACK_SIMULATION'


@dataclass
class ScreenshotDelivery:
    payload: dict
    release: object
    _closed: bool = field(default=False, init=False)
    _release_failed: bool = field(default=False, init=False)
    _lock: object = field(default_factory=threading.RLock, init=False)

    def close(self):
        with self._lock:
            if not self._closed:
                self._closed = True
                try: self.release()
                except Exception: self._release_failed = True
            return not self._release_failed


class _Mailbox:
    def __init__(self):
        self.event = threading.Event(); self.lock = threading.Lock(); self.closed = False; self.delivery = None

    def accept(self, delivery):
        if type(delivery) is not ScreenshotDelivery: return
        with self.lock:
            accepted = not self.closed and self.delivery is None
            if accepted: self.delivery = delivery; self.event.set()
        if not accepted: delivery.close()

    def close(self):
        with self.lock:
            self.closed = True; delivery = self.delivery
        return delivery.close() if delivery is not None else True


def _metadata(meta):
    value = plain_copy(meta)
    require(type(value) is dict and set(value) == {'environment', 'host_device_id', 'boot_session_id', 'observer_session_id', 'window'}, 'INVALID_FRAME')
    for key in ('host_device_id', 'boot_session_id', 'observer_session_id'): require(identifier(value[key]), 'INVALID_FRAME')
    window = value['window']
    require(type(window) is dict and set(window) == {'package', 'window_id', 'display_id', 'type', 'focused', 'active', 'layer', 'covered', 'sensitive'}, 'INVALID_FRAME')
    require(identifier(window['package']) and window['type'] == 'APPLICATION', 'WINDOW_MISMATCH')
    for key in ('window_id', 'display_id', 'layer'): require(type(window[key]) is int, 'INVALID_FRAME')
    for key in ('focused', 'active', 'covered', 'sensitive'): require(type(window[key]) is bool, 'INVALID_FRAME')
    require(window['window_id'] >= 0 and window['display_id'] >= 0, 'INVALID_FRAME')
    require(not window['covered'] and not window['sensitive'], 'BLOCKED_BY_OVERLAY')
    require(window['active'] and window['focused'], 'WINDOW_MISMATCH')
    return value


class ObservationCollector:
    def __init__(self, scope, port, *, authorization=None, budget=None, clock=None):
        self.scope = validate_scope(scope); self.scope_hash = scope_digest(self.scope)
        self.port, self.authorization = port, authorization
        self.clock = clock or (lambda: int(time.monotonic() * 1000))
        self.budget = budget or LearningBudget(self.scope, clock=self.clock)
        self._cancelled = threading.Event(); self._observe_lock = threading.Lock()

    def cancel(self):
        self._cancelled.set(); self.budget.cancel()

    def _check(self, deadline, wall_deadline):
        require(not self._cancelled.is_set(), 'CANCELLED')
        now = self.clock(); require(type(now) is int and now >= 0, 'CLOCK_DOMAIN_ERROR')
        require(now < deadline and time.monotonic() < wall_deadline, 'OBSERVATION_TIMEOUT')
        snapshot = self.budget.snapshot()
        code = {'TIMEOUT': 'OBSERVATION_TIMEOUT', 'CLOCK_ERROR': 'CLOCK_DOMAIN_ERROR'}.get(snapshot['status'], snapshot['status'])
        require(snapshot['status'] == 'RUNNING', code)
        require(snapshot['scope_hash'] == self.scope_hash and snapshot['environment_id'] == self.scope['target']['environment_id'], 'ENVIRONMENT_ERROR')

    def _guard(self, deadline, wall_deadline):
        self._check(deadline, wall_deadline)
        require(scope_digest(self.scope) == self.scope_hash, 'ENVIRONMENT_ERROR')
        require(getattr(self.port, 'channel', None) == 'OFFLINE_CALLBACK_SIMULATION', 'NATIVE_INTEGRATION_UNAVAILABLE')
        auth = self.authorization
        require(type(auth) is ScopeAuthorization and auth.source == 'TEST_FIXTURE_NOT_NATIVE_APPROVAL'
                and auth.scope_hash == self.scope_hash and auth.environment_id == self.scope['target']['environment_id']
                and type(auth.deadline_ms) is int and self.clock() < auth.deadline_ms
                and auth.observe is True and self.scope['requested_permissions']['observe'], 'ENVIRONMENT_ERROR')
        meta = _metadata(self.port.guard())
        self._check(deadline, wall_deadline)
        require(meta['environment'] == self.scope['target'] and meta['host_device_id'] == auth.host_device_id
                and meta['window']['package'] == self.scope['target']['app_package'], 'ENVIRONMENT_ERROR')
        return meta

    def _frame(self, deadline, wall_deadline, attempt_id):
        before = self._guard(deadline, wall_deadline)
        read_started = self.clock()
        raw = plain_copy(self.port.read_frame(deadline, attempt_id))
        self._check(deadline, wall_deadline)
        keys = set(before) | {'elapsed_start_ms', 'elapsed_end_ms', 'uptime_start_ms', 'uptime_end_ms', 'navigation_context', 'tree'}
        require(type(raw) is dict and set(raw) == keys, 'INVALID_FRAME')
        meta = _metadata({key: raw[key] for key in before})
        require(meta == before, 'OBSERVATION_INCONSISTENT')
        for key in ('elapsed_start_ms', 'elapsed_end_ms', 'uptime_start_ms', 'uptime_end_ms'):
            require(type(raw[key]) is int and raw[key] >= 0, 'CLOCK_DOMAIN_ERROR')
        require(read_started <= raw['elapsed_start_ms'] <= raw['elapsed_end_ms'] <= self.clock()
                and raw['elapsed_end_ms'] < deadline
                and raw['uptime_start_ms'] <= raw['uptime_end_ms'], 'CLOCK_DOMAIN_ERROR')
        require(abs((raw['elapsed_end_ms'] - raw['elapsed_start_ms']) -
                    (raw['uptime_end_ms'] - raw['uptime_start_ms'])) <= 10, 'CLOCK_DOMAIN_ERROR')
        nav = raw['navigation_context']
        require(type(nav) is dict and set(nav) == {'tab', 'popup', 'expanded', 'entry', 'visible_slice', 'page_hint'}, 'INVALID_FRAME')
        for key in ('tab', 'popup', 'entry', 'visible_slice', 'page_hint'): require(identifier(nav[key], nullable=True), 'INVALID_FRAME')
        require(type(nav['expanded']) is list and len(nav['expanded']) <= 128 and all(identifier(v) for v in nav['expanded']), 'INVALID_FRAME')
        require(nav['page_hint'] in self.scope['allowed_pages'], 'PAGE_SCOPE_UNCONFIRMED')
        raw['tree'] = copy_tree(raw['tree'])
        require(all(n['package'] == self.scope['target']['app_package'] for n in raw['tree']['nodes']), 'WINDOW_MISMATCH')
        require(raw['tree']['complete'], 'TREE_TRUNCATED')
        return raw

    def _screenshot(self, request_id, a, deadline, wall_deadline, mailbox):
        self._guard(deadline, wall_deadline)
        self.port.request_screenshot(request_id, deadline, mailbox.accept)
        while not mailbox.event.is_set():
            self._check(deadline, wall_deadline)
            mailbox.event.wait(min(0.01, max(0, wall_deadline - time.monotonic())))
        self._check(deadline, wall_deadline)
        packet = plain_copy(mailbox.delivery.payload)
        fields = {'request_id', 'status', 'window_id', 'display_id', 'host_device_id', 'boot_session_id', 'clock_domain',
                  'captured_uptime_ms', 'callback_elapsed_ms', 'evidence_ref', 'sha256', 'dimensions', 'error_code', 'content_check'}
        require(type(packet) is dict and set(packet) == fields, 'INVALID_SCREENSHOT')
        require(packet['request_id'] == request_id, 'OBSERVATION_INCONSISTENT')
        require(packet['status'] in ('AVAILABLE', 'FAILED', 'UNAVAILABLE'), 'INVALID_SCREENSHOT')
        require(identifier(packet['error_code'], nullable=True), 'INVALID_SCREENSHOT')
        require(all(type(packet[k]) is int and packet[k] >= 0 for k in ('window_id', 'display_id')), 'INVALID_SCREENSHOT')
        require(type(packet['callback_elapsed_ms']) is int and a['elapsed_end_ms'] <= packet['callback_elapsed_ms'] <= self.clock()
                and packet['callback_elapsed_ms'] < deadline, 'CLOCK_DOMAIN_ERROR')
        require(packet['window_id'] == a['window']['window_id'] and packet['display_id'] == a['window']['display_id']
                and packet['host_device_id'] == a['host_device_id'] and packet['boot_session_id'] == a['boot_session_id'], 'OBSERVATION_INCONSISTENT')
        if packet['status'] == 'AVAILABLE':
            require(packet['clock_domain'] == 'uptimeMillis' and type(packet['captured_uptime_ms']) is int, 'CLOCK_DOMAIN_ERROR')
            require(identifier(packet['evidence_ref']) and type(packet['sha256']) is str and len(packet['sha256']) == 64
                    and all(c in '0123456789abcdef' for c in packet['sha256']), 'INVALID_SCREENSHOT')
            require(type(packet['dimensions']) is list and len(packet['dimensions']) == 2
                    and all(type(v) is int and 0 < v <= 16384 for v in packet['dimensions']), 'INVALID_SCREENSHOT')
        return packet

    def observe(self, *, screenshot='NONE', total_budget_ms=TOTAL_MS):
        require(screenshot in ('NONE', 'OPTIONAL', 'REQUIRED'), 'INVALID_REQUEST')
        require(type(total_budget_ms) is int and 0 < total_budget_ms <= TOTAL_MS, 'INVALID_REQUEST')
        with self._observe_lock:
            return self._observe(screenshot, total_budget_ms)

    def _observe(self, screenshot, total_ms):
        started = self.clock(); limits = self.budget.snapshot()
        deadline = min(started + total_ms, limits['deadline_ms'])
        wall_deadline = time.monotonic() + max(0, deadline - started) / 1000
        result = {'kind': 'PageObservation', 'schema_version': '1.0', 'observation_id': str(uuid.uuid4()),
                  'environment': self.scope['target'], 'scope_hash': self.scope_hash,
                  'host_device_id': None, 'boot_session_id': None, 'observer_session_id': None,
                  'window_before': None, 'window_after': None, 'started_elapsed_ms': started,
                  'ended_elapsed_ms': None, 'deadline_elapsed_ms': deadline,
                  'capture_status': 'UNCONFIRMED', 'attempts': [], 'tree': None, 'screenshot': None,
                  'navigation_context': None, 'consistency': None,
                  'channel': 'OFFLINE_CALLBACK_SIMULATION', 'producer_version': 'P2_2_1.0',
                  'known_scope': 'NO_VALID_OBSERVATION', 'limitations': ['NOT_ATOMIC_FRAME', 'NOT_LIVE_ANDROID_EVIDENCE'],
                  'execution_authority': False}
        for _ in range(MAX_ATTEMPTS):
            attempt = {'capture_attempt_id': str(uuid.uuid4()), 'capture_status': 'UNCONFIRMED',
                       'deadline_elapsed_ms': deadline, 'tree_a_digest': None, 'tree_b_digest': None}
            result['attempts'].append(attempt); mailbox = _Mailbox()
            try:
                self._guard(deadline, wall_deadline)
                self.budget.charge({'observations': 1}, scope_hash=self.scope_hash,
                                   environment=self.scope['target']['environment_id'])
                a = self._frame(deadline, wall_deadline, attempt['capture_attempt_id'])
                attempt['tree_a_digest'] = a['tree']['full_digest']
                request_id = str(uuid.uuid4())
                packet = self._screenshot(request_id, a, deadline, wall_deadline, mailbox) if screenshot != 'NONE' else None
                b = self._frame(deadline, wall_deadline, attempt['capture_attempt_id'])
                attempt['tree_b_digest'] = b['tree']['full_digest']
                self._guard(deadline, wall_deadline)
                require({k: a[k] for k in ('environment', 'host_device_id', 'boot_session_id', 'observer_session_id', 'window')} ==
                        {k: b[k] for k in ('environment', 'host_device_id', 'boot_session_id', 'observer_session_id', 'window')}, 'OBSERVATION_INCONSISTENT')
                require(abs((b['elapsed_end_ms'] - a['elapsed_start_ms']) -
                            (b['uptime_end_ms'] - a['uptime_start_ms'])) <= 10, 'CLOCK_DOMAIN_ERROR')
                require(a['uptime_end_ms'] <= b['uptime_start_ms']
                        and b['uptime_end_ms'] - a['uptime_start_ms'] <= PAIR_MS
                        and a['navigation_context'] == b['navigation_context']
                        and a['tree']['full_digest'] == b['tree']['full_digest'], 'OBSERVATION_INCONSISTENT')
                pairing, visual, status = 'TREE_A_B_CHECKED', 'NOT_EVALUATED', 'VALID_TREE_ONLY'
                if packet is not None:
                    if packet['status'] != 'AVAILABLE':
                        require(screenshot != 'REQUIRED', 'SCREENSHOT_FAILED'); status = 'PARTIAL_SCREENSHOT_FAILED'
                    else:
                        require(a['uptime_start_ms'] <= packet['captured_uptime_ms'] <= b['uptime_end_ms'], 'OBSERVATION_INCONSISTENT')
                        pairing, status = 'WINDOW_TIME_CHECKED', 'VALID_WINDOW_TIME_CHECKED'
                        check = packet['content_check']
                        if check is not None:
                            require(type(check) is dict and set(check) == {'source', 'facts'}
                                    and check['source'] == 'OFFLINE_SIMULATED_VISUAL_CHECK', 'UNTRUSTED_VISUAL_CLAIM')
                            index = {n['node_local_id']: n for n in b['tree']['nodes']}
                            require(type(check['facts']) is list and 0 < len(check['facts']) <= 128, 'UNTRUSTED_VISUAL_CLAIM')
                            for fact in check['facts']:
                                require(type(fact) is dict and set(fact) == {'node_local_id', 'field', 'value'}, 'UNTRUSTED_VISUAL_CLAIM')
                                require(fact['node_local_id'] in index and fact['field'] in ('text', 'checked', 'range.value'), 'UNTRUSTED_VISUAL_CLAIM')
                                n = index[fact['node_local_id']]
                                actual = n['range']['value'] if fact['field'] == 'range.value' and n['range'] is not None else n.get(fact['field'])
                                require(type(actual) is type(fact['value']) and actual == fact['value'], 'OBSERVATION_INCONSISTENT')
                            pairing, visual, status = 'CONTENT_CHECKED_SIMULATED', 'SIMULATED_NOT_MODEL', 'VALID_CONTENT_CHECKED_SIMULATED'
                attempt['capture_status'] = status
                for key in ('host_device_id', 'boot_session_id', 'observer_session_id'): result[key] = b[key]
                result.update(capture_status=status, tree=b['tree'], screenshot=packet, window_before=a['window'], window_after=b['window'],
                              navigation_context=b['navigation_context'], known_scope=b['tree']['known_scope'],
                              consistency={'pairing_status': pairing, 'visual_content_check': visual,
                                           'tree_a_uptime': [a['uptime_start_ms'], a['uptime_end_ms']],
                                           'tree_b_uptime': [b['uptime_start_ms'], b['uptime_end_ms']]})
                break
            except (ObservationError, ScopeError) as error:
                code = str(error)
                allowed = RETRYABLE | {'ENVIRONMENT_ERROR', 'WINDOW_MISMATCH', 'BLOCKED_BY_OVERLAY', 'CANCELLED',
                    'OBSERVATION_TIMEOUT', 'CLOCK_DOMAIN_ERROR', 'NATIVE_INTEGRATION_UNAVAILABLE', 'INVALID_FRAME',
                    'INVALID_SCREENSHOT', 'SCREENSHOT_FAILED', 'TREE_TRUNCATED', 'BUDGET_EXCEEDED', 'PAGE_SCOPE_UNCONFIRMED',
                    'UNTRUSTED_VISUAL_CLAIM', 'UI_TREE_ERROR', 'WIRE_LIMIT', 'INVALID_DTO', 'BAD_NODE_REFERENCE'}
                if code not in allowed: code = 'CAPTURE_PORT_ERROR'
                attempt['capture_status'] = code; result['capture_status'] = code
                if code not in RETRYABLE: break
            except Exception:
                attempt['capture_status'] = result['capture_status'] = 'CAPTURE_PORT_ERROR'; break
            finally:
                if not mailbox.close():
                    attempt['capture_status'] = result['capture_status'] = 'CAPTURE_RESOURCE_ERROR'
                    result.update(tree=None, screenshot=None, consistency=None, navigation_context=None,
                                  known_scope='NO_VALID_OBSERVATION')
        result['ended_elapsed_ms'] = self.clock()
        result['budget'] = self.budget.snapshot()
        return plain_copy(result)
