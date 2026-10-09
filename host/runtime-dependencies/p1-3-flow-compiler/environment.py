"""Audited adapter description, separate from untrusted knowledge/Flow JSON."""
from dataclasses import dataclass
import json
from pathlib import Path
from dependencies import PINS, canonical, digest, verify_dependencies, contracts


def domain_is_valid(skill, domain):
    try:
        if type(domain) is not dict:
            return False
        cap = contracts.CAPS[skill]
        if set(domain) == {'values'}:
            values = domain['values']
            if type(values) is not list or not 1 <= len(values) <= 256:
                return False
            for value in values:
                contracts._value_domain(value, cap)
            return len({(type(v), v) for v in values}) == len(values)
        if set(domain) != {'min', 'max', 'step'} or cap['type'] != 'integer':
            return False
        low, high, step = domain['min'], domain['max'], domain['step']
        if any(type(v) is not int for v in (low, high, step)) or not (low <= high and 1 <= step <= 2147483647):
            return False
        contracts._value_domain(low, cap)
        contracts._value_domain(high, cap)
        return (high - low) % step == 0
    except (contracts.ContractError, KeyError, TypeError):
        return False


@dataclass(frozen=True)
class EnvironmentProfile:
    _json: str
    source: str

    def to_dict(self):
        return json.loads(self._json)

    @property
    def fingerprint(self):
        return digest({'data': self.to_dict(), 'source': self.source})

    @classmethod
    def test_fixture(cls, value):
        return cls(canonical(value), 'TEST_FIXTURE_NOT_DEVICE_EVIDENCE')


def audited_room_profile():
    verify_dependencies()
    package = json.loads(Path(PINS[3]['path']).read_text(encoding='utf-8'))
    other = json.loads(Path(PINS[4]['path']).read_text(encoding='utf-8'))
    if package != other:
        raise ValueError('SOURCE_PACKAGE_MISMATCH')
    targets = {}
    for row in package['catalog']:
        for cap in row['capabilities']:
            definition = contracts.CAPS[cap['skill']]
            key = row['device'] + '.' + definition['property']
            binding = package['bindings'][key]
            is_power = cap['skill'] == 'SetPower'
            if binding['role'] != ('switch' if is_power else 'slider'):
                raise ValueError('SOURCE_CONTROLLER_MISMATCH')
            targets[key] = {
                'entity_id': row['device'], 'skill': cap['skill'], 'domain': cap['domain'],
                'unit': definition['unit'], 'controller': 'ACTION_CLICK' if is_power else 'ACTION_SET_PROGRESS',
                'reader': 'CHECKED_ON_OFF' if is_power else 'RANGE_INFO_INTEGER',
                'verifier': 'REOBSERVE_EQUALS_AND_PRESERVE_UNMENTIONED',
                'submission': 'DIRECT', 'implemented': True,
            }
    data = {
        'environment': {'environment_id': 'environment.parameter_room',
                        'app_package': package['appPackage'], 'app_version': package['appVersion'],
                        'ui_revision': 'ui.u0'},
        'targets': targets, 'call_protocol': 'semantic_parameter_calls_v2',
        'read_contract': 'semantic_state_read_v1', 'native_flow_read_adapter': False,
        'whole_budget_limit_ms': 8000, 'runtime_local_limit_ms': 10000,
        'source_package_sha256': PINS[3]['sha256'],
    }
    return EnvironmentProfile(canonical(data), 'PINNED_V91_SOURCE_AUDIT_NOT_LIVE_APPROVAL')
