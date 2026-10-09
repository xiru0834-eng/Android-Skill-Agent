"""Inert task-level accounting; never executes, issues permits, or refunds."""
import threading
import time
import uuid

from learning_scope import ScopeError, need, scope_digest, validate_scope

RESOURCES = ('observations', 'actions', 'model_requests', 'storage_bytes')


class LearningBudget:
    def __init__(self, value, *, clock=None):
        scope = validate_scope(value)
        self._scope_hash = scope_digest(scope)
        self._environment = scope['target']['environment_id']
        self._clock = clock or (lambda: int(time.monotonic() * 1000))
        self._started = self._clock()
        need(type(self._started) is int and self._started >= 0, 'INVALID_CLOCK')
        self._last_time = self._started
        self._deadline = self._started + scope['budgets']['max_time_ms']
        self._limits = {key: scope['budgets']['max_' + key] for key in RESOURCES}
        self._spent = dict.fromkeys(RESOURCES, 0)
        self._status = 'RUNNING'
        self._session_id = str(uuid.uuid4())
        self._lock = threading.RLock()

    def _stop(self, reason):
        if self._status == 'RUNNING':
            self._status = reason
        raise ScopeError(self._status)

    def _check(self, scope_hash=None, environment=None):
        if self._status != 'RUNNING':
            raise ScopeError(self._status)
        now = self._clock()
        if type(now) is not int or now < self._last_time:
            self._stop('CLOCK_ERROR')
        self._last_time = now
        if now >= self._deadline:
            self._stop('TIMEOUT')
        if scope_hash is not None and scope_hash != self._scope_hash:
            self._stop('SCOPE_CHANGED')
        if environment is not None and environment != self._environment:
            self._stop('ENVIRONMENT_CHANGED')

    def charge(self, delta, *, scope_hash=None, environment=None):
        need(type(delta) is dict and bool(delta) and set(delta) <= set(RESOURCES), 'INVALID_CHARGE')
        need(all(type(v) is int and 0 <= v <= 67108864 for v in delta.values()), 'INVALID_CHARGE')
        need(any(v > 0 for v in delta.values()), 'INVALID_CHARGE')
        with self._lock:
            self._check(scope_hash, environment)
            if any(self._spent[key] + amount > self._limits[key] for key, amount in delta.items()):
                self._stop('BUDGET_EXCEEDED')
            for key, amount in delta.items():
                self._spent[key] += amount
            return self.snapshot()

    def cancel(self):
        with self._lock:
            if self._status == 'RUNNING':
                self._status = 'CANCELLED'

    def snapshot(self):
        with self._lock:
            try:
                self._check()
            except ScopeError:
                pass
            return {
                'session_id': self._session_id, 'scope_hash': self._scope_hash,
                'environment_id': self._environment, 'status': self._status,
                'started_ms': self._started, 'deadline_ms': self._deadline,
                'spent': dict(self._spent), 'limits': dict(self._limits),
                'execution_authority': False, 'enforcement': 'LOCAL_ACCOUNTING_NOT_RUNTIME_INTEGRATION',
            }
