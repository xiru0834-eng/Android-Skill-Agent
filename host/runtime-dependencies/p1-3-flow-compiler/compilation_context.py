"""Typed, linear lowering. Old contract helpers remain the semantic authority."""
from dependencies import contracts as old


class CompilationContext:
    def __init__(self, flow, task, profile, require, checked):
        self.flow, self.task, self.profile = flow, task, profile
        self.need, self.checked = require, checked
        self.specs = {row['name']: row for row in flow['inputs']}
        self.read_types, self.read_values = {}, {}
        self.deps = set(flow['dependencies']['capabilities'])

    def target(self, target, path):
        cap = self.checked(lambda: old._target(target, self.specs, self.deps), path, 'FLOW')
        entity = self.task['inputs'][target['entity_input']]['entity_id']
        key = entity + '.' + cap['property']
        adapter = self.profile['targets'].get(key)
        self.need(adapter is not None and adapter['implemented'] is True, 'UNSUPPORTED_CAPABILITY', path, 'CAPABILITY')
        self.need(adapter['skill'] == cap['name'] and adapter['entity_id'] == entity, 'CAPABILITY_MISMATCH', path, 'CAPABILITY')
        self.need(adapter['unit'] == cap['unit'], 'UNIT_MISMATCH', path, 'CAPABILITY')
        self.need(adapter['reader'] in ('CHECKED_ON_OFF', 'RANGE_INFO_INTEGER') and
                  adapter['verifier'] == 'REOBSERVE_EQUALS_AND_PRESERVE_UNMENTIONED',
                  'VERIFIER_UNAVAILABLE', path, 'CAPABILITY')
        return key, cap, adapter

    def value(self, ref, path, allow_reads=True):
        reads = self.read_types if allow_reads else {}
        kind = self.checked(lambda: old._value(ref, self.specs, reads, self.deps), path, 'FLOW')
        if ref['kind'] == 'input':
            return {'kind': 'literal', 'value': self.task['inputs'][ref['name']],
                    'type': kind['type'], 'unit': kind.get('unit')}, kind
        if ref['kind'] == 'literal':
            return {'kind': 'literal', 'value': ref['value'], 'type': kind['type'], 'unit': None}, kind
        if ref['kind'] == 'read':
            return {'kind': 'read', 'step_id': ref['step_id'], 'type': kind['type'], 'unit': kind['unit']}, kind
        key, cap, _ = self.target(ref, path)
        return {'kind': ref['kind'], 'key': key, 'type': cap['type'], 'unit': cap['unit']}, kind

    def predicate(self, predicate, path, allow_reads=True):
        keys = ('value',) if predicate['op'] == 'known' else ('left', 'right')
        values = {key: self.value(predicate[key], path + '.' + key, allow_reads)[0] for key in keys}
        self.checked(lambda: old._predicate(predicate, self.specs, self.read_types if allow_reads else {}, self.deps), path, 'FLOW')
        return dict(op=predicate['op'], **values)

    def step(self, step, index):
        path = f'$.steps[{index}]'
        if step['op'] == 'read':
            key, cap, _ = self.target(step['target'], path + '.target')
            self.read_types[step['id']] = cap
            return {'id': step['id'], 'op': 'READ', 'target_key': key, 'type': cap['type'], 'unit': cap['unit']}
        if step['op'] == 'assert':
            return {'id': step['id'], 'op': 'ASSERT', 'predicate': self.predicate(step['predicate'], path + '.predicate')}
        cap = old.CAPS[step['capability']]
        target = {'entity_input': step['entity_input'], 'property': cap['property']}
        key, _, adapter = self.target(target, path + '.capability')
        expected_controller = 'ACTION_CLICK' if cap['name'] == 'SetPower' else 'ACTION_SET_PROGRESS'
        self.need(adapter['controller'] == expected_controller, 'UNSUPPORTED_CONTROLLER', path + '.capability', 'CAPABILITY')
        submission = adapter['submission']
        self.need(submission != 'BUSINESS_PUBLISH', 'UNSUPPORTED_BUSINESS_SUBMISSION', path + '.capability', 'CAPABILITY')
        self.need(submission in ('DIRECT', 'CONTROLLER_INPUT_COMMIT'), 'UNKNOWN_SUBMISSION_SEMANTICS', path + '.capability', 'CAPABILITY')
        self.need(submission != 'CONTROLLER_INPUT_COMMIT' or adapter.get('commit_evidence_verified') is True,
                  'SUBMISSION_EVIDENCE_REQUIRED', path + '.capability', 'CAPABILITY')
        value, source = self.value(step['argument'], path + '.argument')
        self.checked(lambda: old._assignable(source, cap), path + '.argument', 'PARAMETERS')
        self.need(target in self.flow['allowed_effects'], 'CONTRACT_CONFLICT', path, 'FLOW')
        call = None
        if value['kind'] == 'literal':
            check_entity_value(value['value'], cap, adapter['domain'], path + '.argument', self.need, self.checked)
            call = {'skill': cap['name'], 'args': {'device': adapter['entity_id'], cap['argument']: value['value']}}
        return {'id': step['id'], 'op': 'CALL', 'skill': cap['name'], 'entity_id': adapter['entity_id'],
                'argument': cap['argument'], 'target_key': key, 'value': value, 'call': call,
                'domain': adapter['domain'], 'controller': adapter['controller'], 'submission': submission,
                'skip_input_only_if_current_value_equals_target': True,
                'verify_after_call': True, 'business_action_retries': 0}


def check_entity_value(value, cap, domain, path, require, checked):
    checked(lambda: old._value_domain(value, cap), path, 'PARAMETERS')
    accepts = (value in domain['values'] if 'values' in domain else
               domain['min'] <= value <= domain['max'] and (value - domain['min']) % domain['step'] == 0)
    require(accepts, 'ENTITY_DOMAIN_ERROR', path, 'PARAMETERS')
