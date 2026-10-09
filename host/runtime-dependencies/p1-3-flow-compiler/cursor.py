"""Ordered check cursor only; does not dispatch or obtain Android permissions."""
from functools import wraps
from compiler import CompileError, require
from checks import (check_task_policy, materialize_call, evaluate_predicate, observed_value,
                    valid_observation, ReadEvidence, UNKNOWN)


def stop_on_error(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        try:
            require(not self.stopped and not self.finished, 'SESSION_STOPPED', '$', 'CONDITIONS')
            return method(self, *args, **kwargs)
        except CompileError as error:
            self.stopped = True
            if not self.failure:
                self.failure = error.receipt()
            raise
    return call

class CheckCursor:
    def __init__(self, plan, policy_supplier):
        self.plan, self.policy_supplier = plan, policy_supplier
        self.data = plan.to_dict()
        self.index, self.completed_calls, self.sequence = 0, 0, 0
        self.initial, self.pending = None, None
        self.reads, self.expected = {}, {}
        self.stopped, self.finished, self.failure = False, False, None
        self.budget_identity, self.last_now = None, None

    def guard(self, frame, phase, now_ms):
        try:
            policy = self.policy_supplier()
        except Exception:
            raise CompileError('POLICY_CONTEXT_UNAVAILABLE', '$.authorization_ref', 'PERMISSION') from None
        require(type(now_ms) is int and (self.last_now is None or now_ms >= self.last_now),
                'CLOCK_ERROR', '$.budget', 'CONDITIONS')
        check_task_policy(self.plan, policy, now_ms)
        identity = (policy.started_ms, policy.deadline_ms, policy.observation_session_id)
        require(self.budget_identity is None or identity == self.budget_identity,
                'BUDGET_CONTEXT_CHANGED', '$.budget', 'PERMISSION')
        require(valid_observation(self.plan, frame, phase, now_ms, self.sequence),
                'OBSERVATION_UNAVAILABLE', '$.observation', 'CONDITIONS')
        require(frame.observation_session_id == policy.observation_session_id,
                'OBSERVATION_UNAVAILABLE', '$.observation', 'CONDITIONS')
        self.budget_identity, self.last_now = identity, now_ms
        return policy

    def whole_state(self, frame):
        state = {key: observed_value(self.plan, frame, key) for key in self.data['readable_properties']}
        require(all(value is not UNKNOWN for value in state.values()), 'STATE_UNCONFIRMED', '$.observation', 'CONDITIONS')
        return state

    def conditions(self, predicates, frame, phase, now_ms, code):
        for index, predicate in enumerate(predicates):
            result = evaluate_predicate(self.plan, predicate, frame, phase, now_ms, self.initial, self.reads, self.sequence)
            require(result == 'TRUE', code + '_' + result, f'$.{phase.lower()}[{index}]', 'CONDITIONS')

    @stop_on_error
    def start(self, observation, now_ms):
        require(self.initial is None, 'SESSION_ALREADY_STARTED', '$', 'CONDITIONS')
        self.guard(observation, 'ENTRY', now_ms)
        self.initial = observation
        # Check preconditions before demanding a complete preservation snapshot.
        self.conditions(self.data['preconditions'], observation, 'ENTRY', now_ms, 'PRECONDITION')
        self.expected = self.whole_state(observation)
        self.sequence = observation.sequence
        return self.receipt()

    @stop_on_error
    def prepare_next(self, frame, now_ms):
        require(self.initial is not None, 'SESSION_NOT_STARTED', '$', 'CONDITIONS')
        require(self.pending is None, 'STEP_CONFIRMATION_REQUIRED', '$.steps', 'FLOW')
        require(self.index < len(self.data['steps']), 'FLOW_COMPLETE', '$.steps', 'FLOW')
        step = self.data['steps'][self.index]
        policy = self.guard(frame, step['id'], now_ms)
        require(self.whole_state(frame) == self.expected, 'STATE_CHANGED', f'$.steps[{self.index}]', 'CONDITIONS')
        if step['op'] == 'CALL':
            result = materialize_call(self.plan, self.index, frame, policy, now_ms,
                                      self.initial, self.reads, self.sequence)
            self.pending = result['call']['args'][step['argument']]
        else:
            if step['op'] == 'READ':
                self.reads[step['id']] = ReadEvidence(step['id'], frame)
            else:
                self.conditions([step['predicate']], frame, step['id'], now_ms, 'ASSERTION')
            self.index += 1
            result = dict(status='STEP_CHECKED', step_id=step['id'], execution_authority=False)
        self.sequence = frame.sequence
        return result

    @stop_on_error
    def confirm_call(self, frame, now_ms):
        require(self.pending is not None and self.index < len(self.data['steps']), 'NO_PENDING_CALL', '$.steps', 'FLOW')
        step = self.data['steps'][self.index]
        self.guard(frame, 'AFTER.' + step['id'], now_ms)
        state = self.whole_state(frame)
        require(state[step['target_key']] == self.pending, 'VERIFICATION_ERROR', f'$.steps[{self.index}]', 'VERIFICATION')
        for key, previous in self.expected.items():
            if key != step['target_key']:
                require(state[key] == previous, 'FORBIDDEN_SIDE_EFFECT', f'$.steps[{self.index}]', 'VERIFICATION')
        self.expected = state
        self.pending = None
        self.index += 1
        self.completed_calls += 1
        self.sequence = frame.sequence
        return self.receipt()

    @stop_on_error
    def finish(self, frame, now_ms):
        require(self.initial is not None and self.index == len(self.data['steps']) and self.pending is None,
                'FLOW_INCOMPLETE', '$.steps', 'FLOW')
        self.guard(frame, 'FINAL', now_ms)
        require(self.whole_state(frame) == self.expected, 'VERIFICATION_ERROR', '$.goals', 'VERIFICATION')
        self.conditions(self.data['goals'], frame, 'FINAL', now_ms, 'GOAL')
        self.sequence = frame.sequence
        self.finished = True
        return self.receipt()

    def receipt(self):
        return dict(status='CHECK_SEQUENCE_VERIFIED' if self.finished else
                    'CHECK_SEQUENCE_STOPPED' if self.stopped else 'CHECK_SEQUENCE_PENDING',
                    completed_steps=self.index, completed_calls=self.completed_calls,
                    failure=self.failure, execution_authority=False, device_execution_verified=False)
