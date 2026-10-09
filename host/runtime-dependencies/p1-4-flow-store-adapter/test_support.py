"""Handwritten LOGIC_SIMULATION fixtures; never Android state or authority."""
from dataclasses import replace
from p14deps import checks, canonical, digest, environment, compiler

STATE = {'bedroom_light.power': 'off', 'bedroom_light.brightnessPercent': 20,
         'bedroom_ac.power': 'off', 'bedroom_ac.temperatureCelsius': 22}


class Clock:
    def __init__(self):
        self.now = 100

    def __call__(self):
        return self.now


def policy_for(plan, **changes):
    data = plan.to_dict()
    values = dict(plan_hash=digest(data), host_device_id=data['host_device_id'],
                  environment_hash=data['environment_hash'], authorization_ref=data['authorization_ref'],
                  cancellation_token_ref=data['cancellation_token_ref'], allowed_writes=frozenset(data['actual_write_set']),
                  started_ms=0, deadline_ms=8000, max_actions=32, local_approval_verified=True,
                  approved_raw_package_hash=data['source_package_raw_hash'], observation_session_id='test.current.session',
                  source='TEST_FIXTURE_NOT_NATIVE_APPROVAL')
    return checks.PolicyContext(**dict(values, **changes))


class RoomPort:
    """Test-only transport spy. Mutations are dictionary assignments, not UI."""
    channel = 'LOGIC_SIMULATION'

    def __init__(self, clock, state=None):
        self.clock, self.state = clock, dict(STATE if state is None else state)
        self.observations, self.calls, self.sequence = [], [], 0
        self.on_observe = self.on_call = None

    def observe(self, plan, phase):
        self.clock.now += 1
        self.sequence += 1
        if self.on_observe:
            self.on_observe(self, phase)
        data = plan.to_dict()
        self.observations.append(phase)
        return checks.Observation(data['task_id'], data['host_device_id'], data['environment_hash'], phase,
                                  self.sequence, self.clock.now, canonical(self.state), 'test.current.session')

    def run_one(self, call, deadline_ms):
        self.clock.now += 1
        self.calls.append({'call': call, 'deadline_ms': deadline_ms})
        if self.on_call:
            return self.on_call(self, call)
        self.apply(call)
        return {'final_status': 'SUCCESS', 'verification_result': True}

    def apply(self, call):
        data = compiler.old.CAPS[call['skill']]
        self.state[call['args']['device'] + '.' + data['property']] = call['args'][data['argument']]
