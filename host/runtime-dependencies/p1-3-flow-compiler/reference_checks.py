"""Localized diagnostics for existing P1.2 cross-document checks, not new rights."""
from dependencies import contracts as old


def check_cross_references(flow, package, task, require):
    def need(valid, code, path):
        require(valid, code, path, 'FLOW')

    def index(rows, field, path):
        result = {}
        for position, row in enumerate(rows):
            need(row[field] not in result, 'DUPLICATE_ID', f'{path}[{position}].{field}')
            result[row[field]] = row
        return result

    entities = index(package['entities'], 'entity_id', '$.package.entities')
    index(package['bindings'], 'id', '$.package.bindings')
    evidence = index(package['evidence'], 'id', '$.package.evidence')
    index(package['unknowns'], 'id', '$.package.unknowns')
    index(flow['unknowns'], 'id', '$.flow.unknowns')
    need(set(package['documentation_refs']) <= evidence.keys(), 'BAD_REFERENCE', '$.package.documentation_refs')
    for position, binding in enumerate(package['bindings']):
        path = f'$.package.bindings[{position}]'
        need(binding['entity_id'] in entities, 'ENTITY_NOT_FOUND', path + '.entity_id')
        need(old.PROPERTIES[binding['property']]['name'] in entities[binding['entity_id']]['capabilities'],
             'UNSUPPORTED_CAPABILITY', path + '.property')
        need(set(binding['evidence_refs']) <= evidence.keys(), 'BAD_REFERENCE', path + '.evidence_refs')
        x1, y1, x2, y2 = binding['bounds']
        need(x1 <= x2 and y1 <= y2, 'CONSTRAINT_ERROR', path + '.bounds')
    flow_ref = {'id': flow['id'], 'version': flow['version']}
    package_ref = {'id': package['id'], 'version': package['version']}
    need(task['flow_ref'] == flow_ref, 'BAD_REFERENCE', '$.task.flow_ref')
    need(flow_ref in package['flow_refs'], 'BAD_REFERENCE', '$.package.flow_refs')
    need(task['package_ref'] == package_ref, 'BAD_REFERENCE', '$.task.package_ref')
    need(set(flow['evidence_refs']) <= evidence.keys(), 'BAD_REFERENCE', '$.flow.evidence_refs')
    for position, scope in enumerate(flow['verified_scope']):
        path = f'$.flow.verified_scope[{position}]'
        need(scope['environment_ref'] == package['environment']['environment_id'], 'BAD_REFERENCE', path + '.environment_ref')
        need(all(ref in evidence and evidence[ref]['kind'] == 'EXECUTION_REFERENCE' for ref in scope['evidence_refs']),
             'INVALID_EVIDENCE', path + '.evidence_refs')
