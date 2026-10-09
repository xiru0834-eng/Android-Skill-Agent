"""Handwritten TEST_FIXTURE data, never automatic learning or local approval."""
from copy import deepcopy
import json
from pathlib import Path

P12 = Path('D:/Codex-deliveries/smarthome-ui-polish/p1-2-flow-contracts')


def original_bundle():
    return tuple(json.loads((P12 / 'examples' / ('valid-' + name + '.json')).read_text(encoding='utf-8'))
                 for name in ('flow', 'package', 'task'))


def bundle(skill='SetBrightness', value=80):
    flow, package, task = original_bundle()
    snapshot = json.loads((P12 / 'legacy_registry_snapshot.json').read_text(encoding='utf-8'))
    cap = next(d for d in snapshot['definitions'] if d['name'] == skill)
    entity = 'bedroom_ac' if skill == 'SetTemperature' else 'bedroom_light'
    variable = {'name': 'value', 'type': cap['type'], 'default_rule': 'REQUIRE_EXPLICIT', 'unit': cap['unit']}
    if cap['type'] == 'integer':
        variable.update(minimum=cap['minimum'], maximum=cap['maximum'], step=1)
    elif cap['type'] == 'enum':
        variable['choices'] = deepcopy(cap['choices'])
    target = {'entity_input': 'entity', 'property': cap['property']}
    current = dict(kind='state', **target)
    flow.update(purpose='TEST_FIXTURE handwritten compilation only', unknowns=[], verified_scope=[],
                inputs=[{'name': 'entity', 'type': 'entity', 'default_rule': 'REQUIRE_EXPLICIT',
                         'required_capabilities': [skill]}, variable],
                preconditions=[{'op': 'known', 'value': current}],
                steps=[{'id': 'set_value', 'op': 'call', 'capability': skill, 'entity_input': 'entity',
                        'argument': {'kind': 'input', 'name': 'value'}}],
                goals=[{'op': 'equals', 'left': current, 'right': {'kind': 'input', 'name': 'value'}}],
                allowed_effects=[target], must_preserve=[])
    flow['dependencies']['capabilities'] = [skill]
    # The declaration alone is NOT trusted execution support; D layer must check.
    for row in package['entities']:
        if row['entity_id'] == entity and skill not in row['capabilities']:
            row['capabilities'].append(skill)
    task['inputs'] = {'entity': {'entity_id': entity}, 'value': value}
    task['host_device_id'] = 'host.test_fixture'
    task['authorization_ref'] = 'local.test_fixture_not_device_approval'
    return flow, package, task
