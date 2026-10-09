"""Explicit synthetic world. Its hidden routes are never exported to the agent."""
import copy
import uuid
from p23deps import (LearningBudget, ScopeAuthorization, ObservationCollector,
                     validate_scope, scope_digest, derive_page)
from trace_contract import target_for, CHANNEL


class Clock:
    def __init__(self):
        self.now = 1000

    def __call__(self):
        return self.now

    def advance(self, amount):
        self.now += amount


def scope_fixture(**changes):
    scope = {
        'kind': 'LearningScope', 'schema_version': '1.0', 'scope_id': 'learn.trace.fixture',
        'target': {'app_package': 'fixture.navigation', 'app_build': 'fixture.1',
                   'environment_id': 'env.trace', 'ui_revision': 'u0', 'domain': 'EXPERIMENT_APP'},
        'task': {'goal': 'Inspect Room 101', 'entity_types': ['room'], 'known_start_page': 'home',
                 'origin_source_ids': ['src.fixture']},
        'allowed_pages': ['home', 'details', 'info', 'unrelated'],
        'modes': ['HUMAN_DEMO', 'AUTO_UI'],
        'sources': [{'source_id': 'src.fixture', 'mode': 'AUTO_UI', 'actor': 'AUTOMATED', 'channel': 'TEST_FIXTURE',
                     'evidence_ref': 'fixture:source', 'sha256': 'a' * 64,
                     'origin': {'domain': 'EXPERIMENT_APP', 'app_package': 'fixture.navigation', 'app_build': 'fixture.1'}}],
        'requested_permissions': {'observe': True, 'navigation': ['CLICK', 'BACK', 'SCROLL'], 'business_writes': []},
        'authorization_refs': [],
        'budgets': {'max_time_ms': 10000, 'max_observations': 64, 'max_actions': 20,
                    'max_model_requests': 10, 'max_storage_bytes': 2000000}}
    for key, value in changes.items():
        scope[key] = value
    # Keep fixture source/mode pairing strictly compatible with P2.1.
    scope['modes'] = ['AUTO_UI']
    return validate_scope(scope)


def node(local='root', parent=None, **changes):
    result = {'node_local_id': local, 'parent_local_id': parent, 'package': 'fixture.navigation',
              'resource_id': None, 'class_name': 'android.view.ViewGroup', 'role': 'container',
              'text': None, 'content_description': None, 'bounds': [0, 0, 400, 800],
              'visible': True, 'enabled': True, 'clickable': False, 'checkable': False,
              'checked': None, 'selected': False, 'editable': False, 'password': False,
              'heading': False, 'range': None, 'collection': None, 'collection_item': None}
    result.update(changes)
    return result


def action(kind='CLICK', semantic_target='Open details', local='target'):
    return {'kind': kind, 'semantic_target': semantic_target, 'node_local_id': local}


def receipt(before, after, *, status='SENT_SIMULATED', error=None):
    return {'dispatch_id': str(uuid.uuid4()), 'status': status,
            'started_elapsed_ms': before['ended_elapsed_ms'],
            'finished_elapsed_ms': before['ended_elapsed_ms'],
            'clock_domain': 'elapsedRealtime', 'channel': CHANNEL, 'error_code': error}


def write_audit(*, coverage='COMPLETE', committed=0, pending=0):
    return {'coverage': coverage, 'committed': committed, 'pending': pending,
            'evidence_ref': 'fixture:business-journal', 'channel': 'DECLARED_FIXTURE_JOURNAL'}


class World:
    channel = CHANNEL

    def __init__(self, harness):
        self.h = harness
        self.page = 'home'
        self.entity = 'Room 101'
        self.popup = None
        self.entry = None
        self.visible_slice = 'top'
        self.value = 20
        self.dispatches = []
        self.tree_reads = 0
        self.after_dispatch = None
        self.delay_ms = 0
        self.audit = write_audit()
        self.duplicate = False
        self.replace_before_dispatch = False
        self.no_effect = False

    def _nodes(self):
        target_id = {'home': 'fixture:id/open', 'details': 'fixture:id/info',
                     'info': 'fixture:id/back', 'unrelated': 'fixture:id/back'}[self.page]
        result = [node(), node('heading', 'root', role='heading', heading=True,
                              class_name='android.widget.TextView', text=self.entity),
                  node('target', 'root', role='button', clickable=True, resource_id=target_id, text='Details')]
        if self.duplicate:
            result.append(node('duplicate', 'root', role='button', clickable=True, resource_id=target_id, text='Details'))
        return result

    def guard(self):
        return {'environment': self.h.scope['target'], 'host_device_id': 'fixture.host',
                'boot_session_id': 'fixture.boot', 'observer_session_id': 'fixture.observer',
                'window': {'package': 'fixture.navigation', 'window_id': 1, 'display_id': 0,
                           'type': 'APPLICATION', 'focused': True, 'active': True, 'layer': 0,
                           'covered': False, 'sensitive': False}}

    def read_frame(self, deadline_ms, attempt_id):
        self.tree_reads += 1
        start = self.h.clock()
        self.h.clock.advance(5)
        frame = self.guard()
        frame.update(elapsed_start_ms=start, elapsed_end_ms=self.h.clock(),
                     uptime_start_ms=start - 500, uptime_end_ms=self.h.clock() - 500,
                     navigation_context={'tab': None, 'popup': self.popup, 'expanded': [],
                                         'entry': self.entry, 'visible_slice': self.visible_slice, 'page_hint': self.page},
                     tree={'root_readable': True, 'complete': True, 'truncated_reasons': [], 'nodes': self._nodes()})
        return frame

    def request_screenshot(self, request_id, deadline_ms, callback):
        raise AssertionError('This fixture only captures Tree; no pixels or model.')

    def observe(self, deadline_ms=None):
        return self.h.collector.observe()

    def dispatch(self, candidate, dispatch_id, deadline_ms):
        before = self.h.clock()
        self.dispatches.append(copy.deepcopy(candidate))
        self.h.clock.advance(2)
        if not self.no_effect:
            self.page = {'home': 'details', 'details': 'info', 'info': 'details', 'unrelated': 'home'}[self.page]
        if self.after_dispatch:
            self.after_dispatch()
        return {'dispatch_id': dispatch_id, 'status': 'SENT_SIMULATED',
                'started_elapsed_ms': before, 'finished_elapsed_ms': self.h.clock(),
                'clock_domain': 'elapsedRealtime', 'channel': CHANNEL, 'error_code': None}

    def write_audit(self):
        return copy.deepcopy(self.audit)

    def wait(self, millis, deadline_ms):
        self.h.clock.advance(millis)


class CaptureView:
    channel = 'OFFLINE_CALLBACK_SIMULATION'

    def __init__(self, world):
        self.world = world

    def guard(self):
        return self.world.guard()

    def read_frame(self, deadline_ms, attempt_id):
        return self.world.read_frame(deadline_ms, attempt_id)

    def request_screenshot(self, request_id, deadline_ms, callback):
        return self.world.request_screenshot(request_id, deadline_ms, callback)


class Harness:
    def __init__(self, scope=None):
        self.clock = Clock()
        self.scope = scope or scope_fixture()
        self.budget = LearningBudget(self.scope, clock=self.clock)
        self.auth = ScopeAuthorization(scope_digest(self.scope), 'env.trace', 'fixture.host', 11000,
                                       observe=True, navigation=('CLICK', 'BACK', 'SCROLL'), model_requests=10)
        self.world = World(self)
        self.collector = ObservationCollector(self.scope, CaptureView(self.world), authorization=self.auth,
                                              budget=self.budget, clock=self.clock)

    def observe(self, page=None, **changes):
        if page is not None:
            self.world.page = page
        for key, value in changes.items():
            setattr(self.world, key, value)
        return self.world.observe()

    def target(self, obs):
        return target_for(derive_page(obs, entity_types=['room']))
