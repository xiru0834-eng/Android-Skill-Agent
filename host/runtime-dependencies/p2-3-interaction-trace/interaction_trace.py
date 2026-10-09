"""Explicit controlled trajectory session. No Android transport, no real model client."""
import threading
import uuid
from dataclasses import asdict

from p23deps import (ScopeAuthorization, ScopeError, LearningBudget, validate_scope,
                     scope_digest, digest, canonical, derive_page, VALID)
from trace_contract import (TraceError, need, detached, observation, check_target,
                            matches_target, target_for, make_interaction, check_receipt, check_write_audit,
                            CHANNEL, MAX_STEPS)
from navigation_graph import NavigationGraph
from safe_navigation import SafetyPolicy

POST_LIMIT = 4
POST_WAIT_MS = 100
MAX_BUNDLE_BYTES = 3145728


def native_readiness():
    return {'status': 'BLOCKED', 'channel': 'REAL_ANDROID', 'execution_authority': False,
            'gaps': ['P22_NATIVE_OBSERVATION_NOT_WIRED', 'P23_NATIVE_EVENT_ADAPTER_NOT_WIRED',
                     'CURRENT_NATIVE_APPROVAL_NOT_PRESENT', 'FORMAL_DEVICE_GATES_NOT_PASSED'],
            'model_requests': 0, 'device_actions': 0}


class TraceSession:
    def __init__(self, scope, *, authorization, budget, clock, policy, enabled=False, channel=CHANNEL):
        need(enabled is True and channel == CHANNEL, 'FEATURE_DISABLED_OR_UNSUPPORTED_CHANNEL')
        self.scope = detached(validate_scope(scope))
        need(type(authorization) is ScopeAuthorization
             and authorization.source == 'TEST_FIXTURE_NOT_NATIVE_APPROVAL', 'AUTHORIZATION_REQUIRED')
        need(type(budget) is LearningBudget and type(policy) is SafetyPolicy, 'INVALID_SESSION_DEPENDENCY')
        self.authorization, self.budget, self.clock, self.policy = authorization, budget, clock, policy
        self._scope_hash = scope_digest(self.scope)
        self._budget_instance = budget
        self._budget_id = budget.snapshot()['session_id']
        self._auth_hash = digest(asdict(authorization))
        self._policy_hash = digest(policy.snapshot()['rules'])
        requested = self.scope['requested_permissions']
        need(requested['observe'] and authorization.observe is True
             and authorization.scope_hash == self._scope_hash
             and authorization.environment_id == self.scope['target']['environment_id']
             and set(requested['navigation']) <= set(authorization.navigation)
             and not requested['business_writes'], 'AUTHORIZATION_MISMATCH')
        need(budget.snapshot()['scope_hash'] == self._scope_hash, 'BUDGET_SCOPE_MISMATCH')
        self.graph = NavigationGraph(self.scope['task']['entity_types'])
        self.state = 'RUNNING'
        self._id = str(uuid.uuid4())
        self._observations, self._steps, self._attempts, self._diagnostics = {}, [], [], []
        self._forensic_tail_bytes = 0
        self._boot, self._observer = None, None
        self._lock = threading.RLock()
        self._cancelled = threading.Event()
        self._guard()

    def _guard(self):
        need(not self._cancelled.is_set(), 'CANCELLED')
        need(self.state == 'RUNNING', self.state)
        need(self.budget is self._budget_instance and self.budget.snapshot()['session_id'] == self._budget_id,
             'BUDGET_SESSION_CHANGED')
        need(scope_digest(self.scope) == self._scope_hash, 'SCOPE_CHANGED')
        need(digest(asdict(self.authorization)) == self._auth_hash, 'AUTHORIZATION_CHANGED')
        need(digest(self.policy.snapshot()['rules']) == self._policy_hash
             and self.policy.digest == self._policy_hash, 'SAFETY_POLICY_CHANGED')
        status = self.budget.snapshot()['status']
        need(status == 'RUNNING', status)
        need(self.clock() < self.authorization.deadline_ms, 'AUTHORIZATION_EXPIRED')

    def _charge(self, resource, count=1):
        self._guard()
        self.budget.charge({resource: count}, scope_hash=self._scope_hash,
                           environment=self.scope['target']['environment_id'])
        self._guard()

    def _put_observation(self, value):
        value = observation(value)
        need(value['scope_hash'] == self._scope_hash and value['environment'] == self.scope['target']
             and value['host_device_id'] == self.authorization.host_device_id
             and value['budget']['session_id'] == self._budget_id, 'OBSERVATION_CONTEXT_CHANGED')
        if self._boot is None:
            self._boot, self._observer = value['boot_session_id'], value['observer_session_id']
        need((value['boot_session_id'], value['observer_session_id']) == (self._boot, self._observer),
             'OBSERVATION_SESSION_CHANGED')
        oid = value['observation_id']
        if oid in self._observations:
            need(self._observations[oid] == value, 'OBSERVATION_ID_COLLISION')
        else:
            self._charge('storage_bytes', len(canonical(value).encode('utf-8')))
            self._observations[oid] = detached(value)
        return value

    def _collect(self, port):
        self._guard()
        try:
            raw = port.observe(deadline_ms=self._deadline())
        except Exception as error:
            raise TraceError('OBSERVATION_PORT_ERROR') from error
        value = self._put_observation(raw)
        self._guard()
        need(value['capture_status'] in VALID, 'OBSERVATION_UNAVAILABLE')
        page = derive_page(value, entity_types=self.scope['task']['entity_types'])
        need(page['navigation_context']['popup'] is None, 'BLOCKED_BY_OVERLAY')
        need(page['navigation_context']['page_hint'] in self.scope['allowed_pages'], 'PAGE_OUTSIDE_SCOPE')
        need(page['identity_status'] == 'KNOWN', 'IDENTITY_UNCONFIRMED')
        return value, page

    def _deadline(self):
        return min(self.budget.snapshot()['deadline_ms'], self.authorization.deadline_ms)

    def cancel(self):
        # Never hold the session lock: cancellation must reach an in-flight callback.
        self._cancelled.set()
        self.state = 'CANCELLED'
        self._budget_instance.cancel()

    def note_late_callback(self, dispatch_id):
        with self._lock:
            need(any(s['dispatch']['dispatch_id'] == dispatch_id for s in self._steps), 'UNKNOWN_DISPATCH_ID')
            if len(self._diagnostics) < MAX_STEPS:
                self._diagnostics.append({'event': 'LATE_CALLBACK_IGNORED', 'dispatch_id': dispatch_id,
                                          'execution_authority': False})
                self._sync_storage()

    def _evidence_payload(self):
        return {'observations': list(self._observations.values()), 'interactions': self._steps,
                'map': self.graph.snapshot(), 'navigation_attempts': self._attempts,
                'diagnostics': self._diagnostics}

    def _sync_storage(self):
        """Charge all persisted evidence, not just Trees. Bounded failure tail cannot resume work."""
        size = len(canonical(self._evidence_payload()).encode('utf-8'))
        need(size <= MAX_BUNDLE_BYTES, 'BUNDLE_SIZE_LIMIT')
        snap = self.budget.snapshot()
        extra = max(0, size - snap['spent']['storage_bytes'])
        if extra and snap['status'] == 'RUNNING':
            try:
                self.budget.charge({'storage_bytes': extra}, scope_hash=self._scope_hash,
                                   environment=self.scope['target']['environment_id'])
                extra = 0
            except ScopeError as error:
                if not self._cancelled.is_set():
                    self.state = error.code
        self._forensic_tail_bytes = extra

    def _save_step(self, source, before, after, action, receipt, audit, target=None, error=None):
        need(len(self._steps) < MAX_STEPS, 'TRACE_CAPACITY')
        step = make_interaction(source, before, after, action, receipt, audit,
                                entity_types=self.scope['task']['entity_types'],
                                expected_target=target, outcome_error=error)
        need(all(s['dispatch']['dispatch_id'] != receipt['dispatch_id'] for s in self._steps),
             'DUPLICATE_DISPATCH')
        self._steps.append(step)
        self.graph.add_interaction(step, before, after)
        if step['status'] in ('SAFETY_VIOLATION', 'UNCONFIRMED', 'FAILED', 'TIMEOUT', 'CANCELLED'):
            self.state = step['failure_code'] or step['status']
        self._sync_storage()
        return step

    def record_interaction(self, source, before, after, action, receipt, audit, *, expected_target=None):
        """Passive import of explicit fixture evidence; never invokes a port or grants a permit."""
        with self._lock:
            self._guard()
            before = self._put_observation(before)
            after = self._put_observation(after) if after is not None else None
            # Validate before charging: malformed material cannot acquire authority.
            make_interaction(source, before, after, action, receipt, audit,
                             entity_types=self.scope['task']['entity_types'], expected_target=expected_target)
            self._charge('actions')
            return detached(self._save_step(source, before, after, action, receipt, audit, expected_target))

    def _attempt(self, status, **fields):
        result = {'kind': 'NavigationAttempt', 'schema_version': '1.0', 'attempt_id': str(uuid.uuid4()),
                  'channel': CHANNEL, 'status': status, 'planning_observation_id': None,
                  'before_observation_id': None, 'after_observation_id': None,
                  'interaction_id': None, 'post_observations': 0, 'failure_code': None,
                  'execution_authority': False, 'model_calls': 0}
        result.update(fields)
        if len(self._attempts) < MAX_STEPS:
            self._attempts.append(detached(result))
            self._sync_storage()
            if self.budget.snapshot()['status'] == 'BUDGET_EXCEEDED':
                result['status'] = 'BUDGET_EXCEEDED'
                self._attempts[-1]['status'] = 'BUDGET_EXCEEDED'
                self._sync_storage()
        return detached(result)

    def _select(self, obs, proposal, selector):
        choices = self.policy.candidates(obs)
        need(choices['status'] != 'AMBIGUOUS', 'RESOLUTION_AMBIGUOUS')
        items = choices['items']
        if selector is not None:
            need(type(selector) is dict and set(selector) == {'resource_id', 'role'}, 'INVALID_SELECTOR')
            items = [c for c in items if c['selector'] == selector]
        need(bool(items), 'NO_SAFE_CANDIDATES')
        if proposal is None:
            need(len(items) == 1, 'RESOLUTION_AMBIGUOUS')
            return items[0]
        need(getattr(proposal, 'channel', None) == 'FAKE_MODEL', 'REAL_MODEL_DISABLED')
        self._charge('model_requests')
        need(self.budget.snapshot()['spent']['model_requests'] <= self.authorization.model_requests,
             'MODEL_PERMISSION_EXHAUSTED')
        try:
            answer = detached(proposal.choose(detached(obs), detached(items)))
        except Exception as error:
            raise TraceError('MODEL_ERROR') from error
        self._guard()
        need(type(answer) is dict and set(answer) == {'observation_id', 'candidate_id'}
             and answer['observation_id'] == obs['observation_id'], 'MODEL_PROPOSAL_REJECTED')
        matched = [c for c in items if c['candidate_id'] == answer['candidate_id']]
        need(len(matched) == 1, 'MODEL_PROPOSAL_REJECTED')
        return matched[0]

    def navigate_one(self, port, *, target=None, proposal=None, selector=None):
        with self._lock:
            planned, before, after, dispatch, count = None, None, None, None, 0
            target = check_target(target)
            try:
                self._guard()
                need(getattr(port, 'channel', None) == CHANNEL, 'NATIVE_PORT_DISABLED')
                need(proposal is None or getattr(proposal, 'channel', None) == 'FAKE_MODEL', 'REAL_MODEL_DISABLED')
                planned, page = self._collect(port)
                if matches_target(page, target):
                    return self._attempt('ALREADY_AT_TARGET', planning_observation_id=planned['observation_id'])
                candidate = self._select(planned, proposal, selector)
                before, fresh_page = self._collect(port)
                need(target_for(page) == target_for(fresh_page), 'PLANNING_OBSERVATION_CHANGED')
                current = self.policy.candidates(before)
                fresh = [c for c in current['items'] if c['rule_id'] == candidate['rule_id']
                         and c['selector'] == candidate['selector'] and c['kind'] == candidate['kind']]
                need(len(fresh) == 1 and current['status'] != 'AMBIGUOUS', 'STALE_OR_AMBIGUOUS_CANDIDATE')
                candidate = fresh[0]
                need(candidate['kind'] in self.authorization.navigation
                     and candidate['kind'] in self.scope['requested_permissions']['navigation'], 'UNAUTHORIZED_ACTION')
                self._charge('actions')
                nonce = str(uuid.uuid4())
                start = self.clock()
                error = None
                try:
                    dispatch = detached(port.dispatch(detached(candidate), nonce, self._deadline()))
                    need(dispatch.get('dispatch_id') == nonce, 'DISPATCH_RECEIPT_MISMATCH')
                    check_receipt(dispatch, before, None)
                    need(dispatch['finished_elapsed_ms'] <= self.clock(), 'DISPATCH_TIME_ERROR')
                except Exception:
                    dispatch = {'dispatch_id': nonce, 'status': 'UNKNOWN', 'started_elapsed_ms': start,
                                'finished_elapsed_ms': self.clock(), 'clock_domain': 'elapsedRealtime',
                                'channel': CHANNEL, 'error_code': 'DISPATCH_ERROR'}
                    error = 'DISPATCH_ERROR'
                try:
                    self._guard()
                    for count in range(1, POST_LIMIT + 1):
                        after, post = self._collect(port)
                        if target is None or matches_target(post, target):
                            break
                        if count < POST_LIMIT:
                            self._guard()
                            try:
                                port.wait(POST_WAIT_MS, self._deadline())
                            except Exception as issue:
                                raise TraceError('WAIT_PORT_ERROR') from issue
                    self._guard()
                except (TraceError, ScopeError) as issue:
                    error = issue.code
                    after = None
                try:
                    audit = check_write_audit(port.write_audit())
                except Exception:
                    audit = {'coverage': 'UNAVAILABLE', 'committed': 0, 'pending': 0,
                             'evidence_ref': None, 'channel': 'DECLARED_FIXTURE_JOURNAL'}
                act = {'kind': candidate['kind'], 'semantic_target': candidate['semantic_target'],
                       'node_local_id': candidate['node_local_id']}
                step = self._save_step('AGENT_NAVIGATION', before, after, act, dispatch, audit, target, error)
                status = step['status']
                if target is not None and status in ('NO_TRANSITION', 'OBSERVED_SIMULATED'):
                    status = 'UNCONFIRMED'
                return self._attempt(status, planning_observation_id=planned['observation_id'],
                    before_observation_id=before['observation_id'],
                    after_observation_id=after['observation_id'] if after else None,
                    interaction_id=step['interaction_id'], post_observations=count, failure_code=step['failure_code'],
                    model_calls=int(proposal is not None))
            except (TraceError, ScopeError) as error:
                code = error.code
                reject = code in ('MODEL_ERROR', 'MODEL_PROPOSAL_REJECTED', 'REAL_MODEL_DISABLED',
                                  'NATIVE_PORT_DISABLED', 'INVALID_SELECTOR')
                if not reject:
                    self.state = code
                return self._attempt('REJECTED' if reject else code, failure_code=code,
                     planning_observation_id=planned['observation_id'] if planned else None,
                     before_observation_id=before['observation_id'] if before else None,
                     post_observations=count, model_calls=int(proposal is not None and code != 'REAL_MODEL_DISABLED'))

    def navigate_known(self, port, target):
        """Program search; each recorded clue is re-resolved against a new observation."""
        target = check_target(target)
        try:
            self._guard()
            need(getattr(port, 'channel', None) == CHANNEL, 'NATIVE_PORT_DISABLED')
            current, page = self._collect(port)
            route = self.graph.search(page, target)
        except (TraceError, ScopeError) as error:
            return {'status': error.code, 'attempts': [], 'model_calls': 0, 'execution_authority': False}
        attempts = []
        if route['status'] != 'FOUND':
            return {'status': route['status'], 'attempts': [], 'model_calls': 0, 'execution_authority': False}
        for edge in route['edges']:
            result = self.navigate_one(port, target=edge['arrival_condition'],
                selector={key: edge['public_clues'][key] for key in ('resource_id', 'role')})
            attempts.append(result)
            if result['status'] != 'ARRIVAL_VERIFIED_SIMULATED':
                self.graph.invalidate(edge['edge_id'], result['status'])
                return {'status': 'KNOWN_ROUTE_FAILED', 'attempts': attempts, 'model_calls': 0, 'execution_authority': False}
        return {'status': 'ARRIVAL_VERIFIED_SIMULATED', 'attempts': attempts, 'model_calls': 0, 'execution_authority': False}

    def bundle(self):
        value = detached({'kind': 'TraceBundle', 'schema_version': '1.0', 'trace_id': self._id,
                          'channel': CHANNEL, 'state': self.state, 'scope': self.scope,
                          'scope_hash': self._scope_hash, 'budget': self.budget.snapshot(),
                          'safety_policy': self.policy.snapshot(),
                          'observations': list(self._observations.values()), 'interactions': self._steps,
                          'navigation_attempts': self._attempts, 'diagnostics': self._diagnostics,
                          'forensic_tail_bytes': self._forensic_tail_bytes,
                          'source_counts': {s: sum(i['source'] == s for i in self._steps)
                            for s in ('HUMAN_DEMONSTRATION', 'AGENT_NAVIGATION', 'AGENT_BUSINESS_EXECUTION',
                                      'EVALUATOR_INITIALIZATION', 'UNKNOWN')},
                          'map': self.graph.snapshot(), 'execution_authority': False,
                          'native_integration': 'BLOCKED', 'evidence_level': 'NOT_REAL_ANDROID_EVIDENCE'})
        need(len(canonical(value).encode('utf-8')) <= MAX_BUNDLE_BYTES, 'BUNDLE_SIZE_LIMIT')
        return value
