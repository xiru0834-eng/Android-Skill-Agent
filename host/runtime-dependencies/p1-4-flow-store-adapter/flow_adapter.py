"""Default-off coordinator over the pinned P1.3 ordered check cursor.

Local transport is simulation-only. The Android port compiles separately; no
implicit ADB/model/network path or self-reported native evidence is accepted.
"""
from dataclasses import dataclass
import json
import time
import uuid
from p14deps import compiler, checks, cursor, environment, canonical, digest
from flow_store import StoreError
from records import ValidationAuthority, _issue_evidence


@dataclass(frozen=True)
class RunResult:
    receipt: dict
    evidence: object = None


def route_entry(enabled, legacy_entry, flow_entry, original_payload):
    if type(enabled) is not bool:
        raise ValueError('FEATURE_FLAG_TYPE_ERROR')
    return flow_entry(original_payload) if enabled else legacy_entry(original_payload)


class FlowAdapter:
    def __init__(self, enabled=False, profile=None, clock=None):
        if type(enabled) is not bool:
            raise ValueError('FEATURE_FLAG_TYPE_ERROR')
        self.enabled, self.profile = enabled, profile
        self.clock = clock or (lambda: int(time.monotonic() * 1000))

    def validate_candidate(self, store, key, task, authority, policy_supplier, port):
        return self._run(store, key, task, policy_supplier, port, authority, candidate=True)

    def execute_published(self, store, key, task, policy_supplier, port):
        return self._run(store, key, task, policy_supplier, port, None)

    def _run(self, store, key, task, policy_supplier, port, validation_authority, candidate=False):
        receipt = {'channel': 'LOGIC_SIMULATION', 'execution_authority': False,
                   'device_execution_verified': False, 'completed_calls': 0, 'completed_steps': 0,
                   'dispatch_count': 0, 'failure': None, 'last_observed_state': None,
                   'state_current_after_failure': False}
        if not self.enabled:
            return RunResult({**receipt, 'status': 'FEATURE_DISABLED'})
        sequence, frames, dispatches = None, [], []
        try:
            profile = self.profile or environment.audited_room_profile()
            allowed = {'CHECKED', 'VALIDATED_SCOPE'} if candidate else {'PUBLISHED'}
            if candidate:
                if (type(validation_authority) is not ValidationAuthority or validation_authority.confirmed is not True or
                    validation_authority.version_key != key or type(validation_authority.operator_id) is not str or
                    not 0 < len(validation_authority.operator_id) <= 128):
                    raise StoreError('VALIDATION_AUTHORITY_REQUIRED')
            record = store.load(key)
            if record['state'] not in allowed:
                raise StoreError('NOT_CHECKED' if candidate else 'NOT_PUBLISHED')
            plan = compiler.compile_flow(record['flow'], record['package'], task, profile)
            def semantic_state(frame):
                values = {key: checks.observed_value(plan, frame, key) for key in plan.to_dict()['readable_properties']}
                return {key: value for key, value in values.items() if value is not checks.UNKNOWN}
            if getattr(port, 'channel', None) != 'LOGIC_SIMULATION':
                raise StoreError('NATIVE_TRANSPORT_NOT_CONNECTED')

            def guard():
                current = store.load(key)
                if current['sha256'] != record['sha256'] or current['state'] not in allowed:
                    raise StoreError('KNOWLEDGE_REVOKED')
                if current['state'] == 'PUBLISHED' and current['history'][-1]['payload']['environment_hash'] != plan.to_dict()['environment_hash']:
                    raise StoreError('PUBLICATION_ENVIRONMENT_MISMATCH')
                try:
                    policy = policy_supplier()
                except Exception:
                    raise StoreError('POLICY_CONTEXT_UNAVAILABLE') from None
                checks.check_task_policy(plan, policy, self.clock())
                if policy.source != 'TEST_FIXTURE_NOT_NATIVE_APPROVAL':
                    raise StoreError('EVIDENCE_CHANNEL_MISMATCH')
                return policy

            def observe(phase):
                guard()
                try:
                    frame = port.observe(plan, phase)
                except (StoreError, compiler.CompileError):
                    raise
                except Exception:
                    raise StoreError('OBSERVATION_PORT_ERROR') from None
                guard()
                if type(frame) is not checks.Observation:
                    raise StoreError('OBSERVATION_UNAVAILABLE')
                frames.append(frame)
                return frame

            sequence = cursor.CheckCursor(plan, guard)
            entry = observe('ENTRY')
            sequence.start(entry, self.clock())
            while sequence.index < len(sequence.data['steps']):
                step = sequence.data['steps'][sequence.index]
                frame = observe(step['id'])
                materialized = sequence.prepare_next(frame, self.clock())
                if step['op'] != 'CALL':
                    continue
                policy = guard()
                if not materialized['skip_business_input']:
                    dispatches.append(materialized['call'])
                    try:
                        legacy = port.run_one(materialized['call'], policy.deadline_ms)
                    except Exception:
                        raise StoreError('EXECUTION_PORT_ERROR') from None
                    guard()
                    if (type(legacy) is not dict or legacy.get('final_status') not in ('SUCCESS', 'NO_ACTION_REQUIRED') or
                        legacy.get('verification_result') is not True):
                        raise StoreError('LEGACY_RESULT_UNCONFIRMED')
                after = observe('AFTER.' + step['id'])
                sequence.confirm_call(after, self.clock())
            final = observe('FINAL')
            sequence.finish(final, self.clock())
            guard()
            data = plan.to_dict()
            scope = {'evidence_id': 'execution.' + uuid.uuid4().hex, 'channel': 'LOGIC_SIMULATION',
                     'version_sha256': record['sha256'], 'flow_hash': data['flow_hash'], 'package_hash': data['package_hash'],
                     'plan_hash': digest(data), 'registry_hash': data['registry_hash'],
                     'environment_hash': data['environment_hash'], 'environment': data['environment'],
                     'source_package_raw_hash': data['source_package_raw_hash'], 'host_device_id': data['host_device_id'],
                     'inputs': json.loads(canonical(task['inputs'])), 'initial_state': semantic_state(entry),
                     'final_state': semantic_state(final), 'ordered_calls': dispatches,
                     'sequence_verified': True, 'verifier': 'P1_3_CHECK_CURSOR_FRESH_AFTER_EACH_CALL',
                     'read_only_target_satisfied': not dispatches, 'parameter_domain_verified': False,
                     'observation_sequences': [f.sequence for f in frames], 'observation_times_ms': [f.captured_ms for f in frames],
                     'task_budget_ms': data['task_budget']['duration_ms'], 'execution_authority': False,
                     'device_execution_verified': False}
            return RunResult({**receipt, **sequence.receipt(), 'status': 'SIMULATION_VERIFIED',
                              'dispatch_count': len(dispatches), 'last_observed_state': semantic_state(final),
                              'state_current_after_failure': False}, _issue_evidence(scope))
        except (StoreError, compiler.CompileError) as error:
            failure = error.receipt() if isinstance(error, compiler.CompileError) else {'code': error.code}
            progress = sequence.receipt() if sequence else {}
            last = frames[-1] if frames else None
            return RunResult({**receipt, **progress, 'status': 'UNCONFIRMED' if dispatches else 'REJECTED',
                              'dispatch_count': len(dispatches), 'failure': failure,
                              'last_observed_state': semantic_state(last) if last else None,
                              'last_observed_ms': last.captured_ms if last else None,
                              'state_current_after_failure': False})
