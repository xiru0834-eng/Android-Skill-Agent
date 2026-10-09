"""P1.3 static compilation only; compiled data never grants input authority."""
from dataclasses import dataclass
import json
from dependencies import contracts as old, canonical, digest
from environment import audited_room_profile, EnvironmentProfile, domain_is_valid
from compilation_context import CompilationContext
from reference_checks import check_cross_references

class CompileError(ValueError):
    def __init__(self, code, path='$', layer='FLOW'):
        self.code, self.path, self.layer = code, path, layer
        super().__init__(f'{code} at {path}')

    def receipt(self):
        return dict(status='REJECTED', code=self.code, path=self.path, layer=self.layer,
                    execution_authority=False, ready_for_device_execution=False)


def require(valid, code, path, layer):
    if not valid:
        raise CompileError(code, path, layer)


def checked(function, path, layer):
    try:
        return function()
    except old.ContractError as error:
        raise CompileError(error.code, path if error.path == '$' else error.path, layer) from None


@dataclass(frozen=True)
class CompiledPlan:
    _json: str

    def to_dict(self):
        return json.loads(self._json)


def compile_flow(flow, package, task, environment):
    for doc, kind, path in ((flow, 'FlowSkill', '$.flow'), (package, 'AppKnowledgePackage', '$.package'),
                            (task, 'Task', '$.task')):
        checked(lambda: old._budget(doc), path, 'FORMAT')
        require(type(doc) is dict, 'TYPE_MISMATCH', path, 'FORMAT')
        require('kind' in doc and 'schema_version' in doc, 'MISSING_FIELD', path, 'FORMAT')
        require(type(doc['kind']) is str and type(doc['schema_version']) is str, 'TYPE_MISMATCH', path, 'FORMAT')
        require(doc['kind'] == kind, 'TYPE_MISMATCH', path + '.kind', 'FORMAT')
        require(doc['schema_version'] == '1.0', 'UNSUPPORTED_VERSION', path + '.schema_version', 'FORMAT')
        checked(lambda: old._shape(doc, old.SPEC['roots'][kind], path), path, 'FORMAT')
    check_cross_references(flow, package, task, require)
    specs = {row['name']: row for row in flow['inputs']}
    require(len(specs) == len(flow['inputs']), 'DUPLICATE_ID', '$.inputs', 'FLOW')
    require(set(specs) == set(task['inputs']), 'BAD_REFERENCE', '$.task.inputs', 'PARAMETERS')
    for name, value in task['inputs'].items():
        checked(lambda: old._value_domain(value, specs[name]), '$.task.inputs.' + name, 'PARAMETERS')
    if environment is None:
        environment = audited_room_profile()
    require(type(environment) is EnvironmentProfile, 'UNTRUSTED_ENVIRONMENT', '$.environment', 'CAPABILITY')
    profile = environment.to_dict()
    for key, target in profile['targets'].items():
        require(domain_is_valid(target['skill'], target['domain']), 'ENVIRONMENT_DOMAIN_INVALID', '$.environment.targets', 'CAPABILITY')
    require(package['environment'] == profile['environment'], 'ENVIRONMENT_MISMATCH', '$.package.environment', 'CAPABILITY')
    require(flow['dependencies']['registry_sha256'] == old.SNAPSHOT['registry_sha256'], 'DEPENDENCY_MISMATCH', '$.dependencies.registry_sha256', 'FLOW')
    for dependency in ('call_protocol', 'read_contract'):
        require(flow['dependencies'][dependency] == profile[dependency], 'DEPENDENCY_MISMATCH', '$.dependencies.' + dependency, 'FLOW')
    # Entity bindings are checked before lowering so missing entities never cause KeyError.
    entities = {row['entity_id']: row for row in package['entities']}
    require(task['host_device_id'] not in entities, 'ENTITY_HOST_CONFUSION', '$.task.host_device_id', 'PARAMETERS')
    for name, spec in specs.items():
        if spec['type'] == 'entity':
            entity = task['inputs'][name]['entity_id']
            require(entity in entities, 'ENTITY_NOT_FOUND', '$.task.inputs.' + name, 'PARAMETERS')
            require(set(spec['required_capabilities']) <= set(entities[entity]['capabilities']), 'UNSUPPORTED_CAPABILITY', '$.task.inputs.' + name, 'PARAMETERS')
    context = CompilationContext(flow, task, profile, require, checked)
    preconditions = [context.predicate(p, f'$.preconditions[{i}]', False) for i, p in enumerate(flow['preconditions'])]
    steps = []
    ids, calls = set(), 0
    for index, step in enumerate(flow['steps']):
        path = f'$.steps[{index}]'
        require(step['id'] not in ids, 'DUPLICATE_ID', path + '.id', 'FLOW')
        ids.add(step['id'])
        calls += step['op'] == 'call'
        require(calls <= 32, 'CALL_LIMIT', path, 'FLOW')
        steps.append(context.step(step, index))
    goals = [context.predicate(p, f'$.goals[{i}]', False) for i, p in enumerate(flow['goals'])]
    final_values = {step['target_key']: step['value'] for step in steps if step['op'] == 'CALL'}
    for index, goal in enumerate(goals):
        if goal['op'] == 'equals':
            left, right = goal['left'], goal['right']
            if right['kind'] == 'state':
                left, right = right, left
            assigned = final_values.get(left.get('key')) if left['kind'] == 'state' else None
            if assigned and assigned['kind'] == right['kind'] == 'literal':
                require(type(assigned['value']) is type(right['value']) and assigned['value'] == right['value'],
                        'CONTRACT_CONFLICT', f'$.goals[{index}]', 'FLOW')
    # Preserve every P1.2 semantic/evidence check after adding localized diagnostics.
    summary = checked(lambda: old.validate_bundle(flow, package, task), '$.flow', 'FLOW')
    must_preserve = [context.target(t, f'$.must_preserve[{i}]')[0] for i, t in enumerate(flow['must_preserve'])]
    writes = sorted({s['target_key'] for s in steps if s['op'] == 'CALL'})
    readable = sorted(profile['targets'])
    return CompiledPlan(canonical({
        'kind': 'CompiledFlow', 'version': '1.0', 'status': 'COMPILED_WITH_BLOCKERS' if summary['blocking_unknowns'] else 'COMPILED',
        'validation_layers': ['FORMAT', 'PARAMETERS', 'FLOW', 'CAPABILITY'],
        'permission_state': 'NOT_EVALUATED', 'execution_authority': False, 'ready_for_device_execution': False,
        'flow_hash': digest(flow), 'package_hash': digest(package), 'task_hash': digest(task),
        'environment_hash': environment.fingerprint, 'environment_source': environment.source,
        'source_package_raw_hash': profile['source_package_sha256'],
        'environment': profile['environment'], 'registry_hash': old.SNAPSHOT['registry_sha256'],
        'host_device_id': task['host_device_id'], 'task_id': task['id'],
        'authorization_ref': task['authorization_ref'], 'cancellation_token_ref': task['cancellation_token_ref'],
        'task_budget': task['budget'], 'whole_budget_limit_ms': profile['whole_budget_limit_ms'],
        'runtime_local_limit_ms': profile['runtime_local_limit_ms'],
        'preconditions': preconditions, 'steps': steps, 'goals': goals, 'call_count': calls,
        'actual_write_set': writes, 'must_preserve': must_preserve,
        'preserve_unmentioned': sorted(set(readable) - set(writes)), 'readable_properties': readable,
        'state_contracts': {key: {'skill': value['skill'], 'domain': value['domain']} for key, value in profile['targets'].items()},
        'blocking_unknowns': summary['blocking_unknowns'],
        'pending_checks': ['LOCAL_TASK_POLICY_REQUIRED', 'FRESH_STEP_OBSERVATIONS_REQUIRED',
                           'ANDROID_FLOW_BRIDGE_NOT_IMPLEMENTED', 'DEVICE_EXECUTION_NOT_TESTED'],
    }))
