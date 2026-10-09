"""P1.2 local JSON contract checking only. Never executes or grants authority.

This is a bounded interpreter for our fixed contract_spec.json grammar, not
a general JSON Schema library, Flow compiler, authorization or device adapter.
"""
import argparse
import json
from pathlib import Path
import re
import sys

BASE = Path(__file__).resolve().parent
SPEC = json.loads((BASE / 'contract_spec.json').read_text(encoding='utf-8'))
SNAPSHOT = json.loads((BASE / 'legacy_registry_snapshot.json').read_text(encoding='utf-8'))
CAPS = {d['name']: d for d in SNAPSHOT['definitions']}
PROPERTIES = {d['property']: d for d in SNAPSHOT['definitions']}


class ContractError(ValueError):
    execution_authority = False

    def __init__(self, code, path='$'):
        self.code, self.path = code, path
        super().__init__(f'{code} at {path}')


def need(condition, code, path='$'):
    if not condition:
        raise ContractError(code, path)


def _budget(value):
    """Count JSON values/containers, not dict keys; reject cycles and non-JSON."""
    stack, count, text_size = [(value, 1, frozenset())], 0, 0
    while stack:
        item, depth, ancestors = stack.pop()
        count += 1
        need(depth <= SPEC['limits']['json_depth'] and count <= SPEC['limits']['json_nodes'], 'INPUT_LIMIT')
        need(type(item) in (dict, list, str, int, float, bool, type(None)), 'TYPE_MISMATCH')
        if type(item) in (dict, list):
            need(id(item) not in ancestors, 'INPUT_LIMIT')
            parents = ancestors | {id(item)}
            # Bound queued work before extending, not after allocating a huge stack.
            need(count + len(stack) + len(item) <= SPEC['limits']['json_nodes'], 'INPUT_LIMIT')
            if type(item) is dict:
                need(all(type(k) is str for k in item), 'TYPE_MISMATCH')
                need(all(len(k) <= SPEC['limits']['input_bytes'] for k in item), 'INPUT_LIMIT')
                text_size += sum(len(k) for k in item)
                children = item.values()
            else:
                children = item
            stack.extend((v, depth + 1, parents) for v in children)
        elif type(item) is str:
            need(len(item) <= SPEC['limits']['input_bytes'], 'INPUT_LIMIT')
            text_size += len(item)
        elif type(item) is int:
            # json.loads already bounds decimal conversion; protect the object API too.
            need(item.bit_length() <= SPEC['limits']['integer_bits'], 'INPUT_LIMIT')
        need(text_size <= SPEC['limits']['input_bytes'], 'INPUT_LIMIT')
    try:
        size = len(json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8'))
    except (ValueError, UnicodeError):
        raise ContractError('INVALID_JSON') from None
    need(size <= SPEC['limits']['input_bytes'], 'INPUT_LIMIT')


def parse_document(raw):
    need(type(raw) in (bytes, str), 'TYPE_MISMATCH')
    try:
        encoded = raw if type(raw) is bytes else raw.encode('utf-8')
        need(len(encoded) <= SPEC['limits']['input_bytes'], 'INPUT_LIMIT')

        def unique(pairs):
            obj = {}
            for key, value in pairs:
                need(key not in obj, 'DUPLICATE_FIELD')
                obj[key] = value
            return obj

        def invalid_constant(_):
            raise ContractError('INVALID_JSON')

        doc = json.loads(encoded.decode('utf-8'), object_pairs_hook=unique, parse_constant=invalid_constant)
    except (ValueError, UnicodeError, RecursionError) as error:
        if isinstance(error, ContractError):
            raise
        raise ContractError('INVALID_JSON') from None
    _budget(doc)
    return doc


def _shape(value, rule, path='$'):
    if 'ref' in rule:
        try:
            _shape(value, SPEC['definitions'][rule['ref']], path)
        except ContractError as error:
            code = {'capability': 'UNKNOWN_CAPABILITY', 'property': 'UNKNOWN_PROPERTY'}.get(rule['ref'])
            if code and error.code == 'CONSTRAINT_ERROR':
                raise ContractError(code, path) from None
            raise
        return
    if 'const' in rule:
        need(type(value) is type(rule['const']) and value == rule['const'], 'CONSTRAINT_ERROR', path)
    elif 'record' in rule:
        need(type(value) is dict, 'TYPE_MISMATCH', path)
        fields = rule['record']
        # Do not echo untrusted extra field names or values in diagnostics.
        need(not (set(value) - set(fields)), 'UNKNOWN_FIELD', path)
        need(set(fields) <= set(value), 'MISSING_FIELD', path)
        for key, child in fields.items():
            _shape(value[key], child, path + '.' + key)
    elif 'tag' in rule:
        need(type(value) is dict, 'TYPE_MISMATCH', path)
        tag = rule['tag']
        need(tag in value, 'MISSING_FIELD', path)
        need(type(value[tag]) is str, 'TYPE_MISMATCH', path)
        need(value[tag] in rule['variants'], 'UNSUPPORTED_STEP' if tag == 'op' else 'CONSTRAINT_ERROR', path)
        _shape(value, rule['variants'][value[tag]], path)
    elif 'union' in rule:
        for child in rule['union']:
            try:
                _shape(value, child, path)
                return
            except ContractError:
                pass
        raise ContractError('TYPE_MISMATCH', path)
    elif 'list' in rule:
        need(type(value) is list, 'TYPE_MISMATCH', path)
        need(rule['min'] <= len(value) <= rule['max'], 'CONSTRAINT_ERROR', path)
        if rule['unique']:
            encoded = [json.dumps(v, sort_keys=True, ensure_ascii=True) for v in value]
            need(len(set(encoded)) == len(encoded), 'CONSTRAINT_ERROR', path)
        for i, item in enumerate(value):
            _shape(item, rule['list'], f'{path}[{i}]')
    elif 'map' in rule:
        need(type(value) is dict, 'TYPE_MISMATCH', path)
        need(rule.get('min', 0) <= len(value) <= rule['max'], 'CONSTRAINT_ERROR', path)
        for key, item in value.items():
            _shape(key, rule['keys'], path)
            _shape(item, rule['map'], path + '.' + key)
    else:
        expected = {'string': str, 'integer': int, 'boolean': bool}[rule['type']]
        need(type(value) is expected, 'TYPE_MISMATCH', path)
        if expected is str:
            need(rule.get('min_length', 0) <= len(value) <= rule.get('max_length', 2000), 'CONSTRAINT_ERROR', path)
            if 'pattern' in rule:
                need(re.fullmatch(rule['pattern'], value) is not None, 'CONSTRAINT_ERROR', path)
        if expected is int:
            need(rule.get('min', value) <= value <= rule.get('max', value), 'CONSTRAINT_ERROR', path)
        if 'enum' in rule:
            need(value in rule['enum'], 'CONSTRAINT_ERROR', path)


def _index(items, key):
    result = {}
    for item in items:
        need(item[key] not in result, 'DUPLICATE_ID')
        result[item[key]] = item
    return result


def _target(target, inputs, dependencies):
    name = target['entity_input']
    need(name in inputs, 'BAD_REFERENCE')
    need(inputs[name]['type'] == 'entity', 'TYPE_MISMATCH')
    capability = PROPERTIES[target['property']]
    need(capability['name'] in inputs[name]['required_capabilities'] and capability['name'] in dependencies, 'BAD_REFERENCE')
    return capability


def _value(ref, inputs, reads, dependencies):
    kind = ref['kind']
    if kind == 'literal':
        return {'type': 'integer' if type(ref['value']) is int else 'literal_string', 'unit': None, 'literal': ref['value']}
    if kind == 'input':
        need(ref['name'] in inputs, 'BAD_REFERENCE')
        return inputs[ref['name']]
    if kind == 'read':
        need(ref['step_id'] in reads, 'BAD_REFERENCE')
        return reads[ref['step_id']]
    return _target(ref, inputs, dependencies)


def _value_domain(value, domain):
    kind = domain['type']
    if kind == 'integer':
        need(type(value) is int, 'TYPE_MISMATCH')
        need(domain['minimum'] <= value <= domain['maximum'], 'CONSTRAINT_ERROR')
        need((value - domain['minimum']) % domain.get('step', 1) == 0, 'CONSTRAINT_ERROR')
    elif kind in ('enum', 'identifier'):
        need(type(value) is str, 'TYPE_MISMATCH')
        need(value in domain['choices'] if kind == 'enum' else re.fullmatch('[a-z][a-z0-9_]{0,31}', value) is not None, 'CONSTRAINT_ERROR')
    else:
        need(type(value) is dict and set(value) == {'entity_id'}, 'TYPE_MISMATCH')


def _assignable(source, destination):
    if 'literal' in source:
        _value_domain(source['literal'], destination)
        return
    need(source['type'] == destination['type'] and source.get('unit') == destination.get('unit'), 'TYPE_MISMATCH')
    if source['type'] == 'integer':
        need(source['minimum'] >= destination['minimum'] and source['maximum'] <= destination['maximum'], 'CONSTRAINT_ERROR')
    if source['type'] == 'enum':
        need(set(source['choices']) <= set(destination['choices']), 'CONSTRAINT_ERROR')


def _predicate(predicate, inputs, reads, dependencies):
    if predicate['op'] == 'known':
        _value(predicate['value'], inputs, reads, dependencies)
        return
    left = _value(predicate['left'], inputs, reads, dependencies)
    right = _value(predicate['right'], inputs, reads, dependencies)
    if 'literal' in left and 'literal' in right:
        need(type(left['literal']) is type(right['literal']), 'TYPE_MISMATCH')
    elif 'literal' in left:
        _assignable(left, right)
    elif 'literal' in right:
        _assignable(right, left)
    else:
        need(left['type'] == right['type'] and left.get('unit') == right.get('unit'), 'TYPE_MISMATCH')


def _flow(flow):
    need(flow['dependencies']['registry_sha256'] == SNAPSHOT['registry_sha256'], 'DEPENDENCY_MISMATCH')
    inputs = _index(flow['inputs'], 'name')
    _index(flow['unknowns'], 'id')
    for input_spec in inputs.values():
        if input_spec['type'] == 'integer':
            need(input_spec['minimum'] <= input_spec['maximum'], 'CONSTRAINT_ERROR')
    deps = set(flow['dependencies']['capabilities'])
    for predicate in flow['preconditions']:
        _predicate(predicate, inputs, {}, deps)
    effects = {(t['entity_input'], t['property']) for t in flow['allowed_effects']}
    preserved = {(t['entity_input'], t['property']) for t in flow['must_preserve']}
    need(not effects.intersection(preserved), 'CONTRACT_CONFLICT')
    for target in flow['allowed_effects'] + flow['must_preserve']:
        _target(target, inputs, deps)
    reads, ids, calls = {}, set(), 0
    for step in flow['steps']:
        need(step['id'] not in ids, 'DUPLICATE_ID')
        ids.add(step['id'])
        if step['op'] == 'read':
            reads[step['id']] = _target(step['target'], inputs, deps)
        elif step['op'] == 'assert':
            _predicate(step['predicate'], inputs, reads, deps)
        else:
            calls += 1
            need(calls <= SPEC['limits']['call_count'], 'CALL_LIMIT')
            cap = CAPS[step['capability']]
            target = {'entity_input': step['entity_input'], 'property': cap['property']}
            _target(target, inputs, deps)
            need((target['entity_input'], target['property']) in effects, 'CONTRACT_CONFLICT')
            _assignable(_value(step['argument'], inputs, reads, deps), cap)
    for predicate in flow['goals']:
        # Final goals must use current-state/initial/input values, never old read refs.
        _predicate(predicate, inputs, {}, deps)
        operands = [predicate['value']] if predicate['op'] == 'known' else [predicate['left'], predicate['right']]
        need(any(value['kind'] == 'state' for value in operands), 'CONTRACT_CONFLICT')
    for scope in flow['verified_scope']:
        _inputs(scope['inputs'], inputs)
    return {'call_count': calls, 'step_ids': [step['id'] for step in flow['steps']], 'blocking_unknowns': [item['id'] for item in flow['unknowns'] if item['impact'] == 'BLOCKS_EXECUTION']}


def _package(package):
    entities = _index(package['entities'], 'entity_id')
    _index(package['bindings'], 'id')
    evidence = _index(package['evidence'], 'id')
    _index(package['unknowns'], 'id')
    need(set(package['documentation_refs']) <= evidence.keys(), 'BAD_REFERENCE')
    for binding in package['bindings']:
        need(binding['entity_id'] in entities, 'ENTITY_NOT_FOUND')
        need(PROPERTIES[binding['property']]['name'] in entities[binding['entity_id']]['capabilities'], 'UNSUPPORTED_CAPABILITY')
        need(set(binding['evidence_refs']) <= evidence.keys(), 'BAD_REFERENCE')
        x1, y1, x2, y2 = binding['bounds']
        need(x1 <= x2 and y1 <= y2, 'CONSTRAINT_ERROR')


def _inputs(values, definitions, entities=None, host=None):
    need(set(values) == set(definitions), 'BAD_REFERENCE')
    for name, value in values.items():
        definition = definitions[name]
        _value_domain(value, definition)
        if definition['type'] == 'entity' and entities is not None:
            need(value['entity_id'] != host, 'ENTITY_HOST_CONFUSION')
            need(value['entity_id'] in entities, 'ENTITY_NOT_FOUND')
            need(set(definition['required_capabilities']) <= set(entities[value['entity_id']]['capabilities']), 'UNSUPPORTED_CAPABILITY')


def _summary(kind):
    return {
        'status': 'CONTRACT_VALID', 'kind': kind, 'contract_version': '1.0',
        'validation_scope': 'STRUCTURE_TYPES_AND_STATIC_REFERENCES_ONLY',
        'execution_authority': False, 'authorization_state': 'NOT_EVALUATED',
        'ready_for_device_execution': False,
        'pending_checks': [
            'FULL_FLOW_COMPILATION_NOT_IMPLEMENTED',
            'LOCAL_AUTHORIZATION_NOT_EVALUATED',
            'ENTITY_RUNTIME_DOMAIN_NOT_EVALUATED',
            'RUNTIME_BUDGET_NOT_EVALUATED',
            'ANDROID_READ_ADAPTER_NOT_IMPLEMENTED',
            'DEVICE_EXECUTION_NOT_TESTED',
        ],
    }


def validate_document(doc):
    _budget(doc)
    need(type(doc) is dict, 'TYPE_MISMATCH')
    need('kind' in doc and 'schema_version' in doc, 'MISSING_FIELD')
    need(type(doc['kind']) is str and type(doc['schema_version']) is str, 'TYPE_MISMATCH')
    need(doc['kind'] in SPEC['roots'] and doc['schema_version'] == SPEC['version'], 'UNSUPPORTED_VERSION')
    _shape(doc, SPEC['roots'][doc['kind']])
    result = _summary(doc['kind'])
    if doc['kind'] == 'FlowSkill':
        result.update(_flow(doc))
    elif doc['kind'] == 'AppKnowledgePackage':
        _package(doc)
    return result


def validate_bundle(flow, package, task):
    for doc, kind in ((flow, 'FlowSkill'), (package, 'AppKnowledgePackage'), (task, 'Task')):
        validate_document(doc)
        need(doc['kind'] == kind, 'TYPE_MISMATCH')
    flow_ref = {'id': flow['id'], 'version': flow['version']}
    package_ref = {'id': package['id'], 'version': package['version']}
    need(task['flow_ref'] == flow_ref and flow_ref in package['flow_refs'] and task['package_ref'] == package_ref, 'BAD_REFERENCE')
    entities = _index(package['entities'], 'entity_id')
    need(task['host_device_id'] not in entities, 'ENTITY_HOST_CONFUSION')
    _inputs(task['inputs'], _index(flow['inputs'], 'name'), entities, task['host_device_id'])
    def actual_targets(targets):
        return {(task['inputs'][target['entity_input']]['entity_id'], target['property']) for target in targets}
    # Distinct formal names can refer to the same business entity in this Task.
    need(not actual_targets(flow['allowed_effects']).intersection(actual_targets(flow['must_preserve'])), 'CONTRACT_CONFLICT')
    evidence = _index(package['evidence'], 'id')
    need(set(flow['evidence_refs']) <= evidence.keys(), 'BAD_REFERENCE')
    for scope in flow['verified_scope']:
        need(scope['environment_ref'] == package['environment']['environment_id'], 'BAD_REFERENCE')
        need(all(ref in evidence and evidence[ref]['kind'] == 'EXECUTION_REFERENCE' for ref in scope['evidence_refs']), 'INVALID_EVIDENCE')
    result = _summary('CONTRACT_BUNDLE')
    result.update(_flow(flow))
    result['blocking_unknowns'] += [item['id'] for item in package['unknowns'] if item['impact'] == 'BLOCKS_EXECUTION']
    return result


def _load(path):
    try:
        with Path(path).open('rb') as file:
            raw = file.read(SPEC['limits']['input_bytes'] + 1)
    except OSError:
        raise ContractError('FILE_ERROR') from None
    return parse_document(raw)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline P1.2 contracts only; never executes.')
    commands = parser.add_subparsers(dest='command', required=True)
    check = commands.add_parser('check')
    check.add_argument('document')
    bundle = commands.add_parser('bundle')
    for name in ('flow', 'package', 'task'):
        bundle.add_argument('--' + name, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'check':
            result = validate_document(_load(args.document))
        else:
            result = validate_bundle(_load(args.flow), _load(args.package), _load(args.task))
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except ContractError as error:
        print(json.dumps({'status': 'CONTRACT_INVALID', 'code': error.code, 'path': error.path, 'execution_authority': False, 'ready_for_device_execution': False}))
        return 2


if __name__ == '__main__':
    sys.exit(main())
