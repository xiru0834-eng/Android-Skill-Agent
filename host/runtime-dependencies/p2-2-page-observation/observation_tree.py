"""Bounded public Tree DTOs, not Android node handles, facts, or action permits."""
import json
import math
import re
import uuid

from p22deps import canonical, digest

MAX_NODES, MAX_DEPTH, MAX_TEXT = 2048, 64, 256
MAX_WIRE_BYTES = 3 * 1024 * 1024
FIELDS = {'node_local_id', 'parent_local_id', 'package', 'resource_id', 'class_name',
          'role', 'text', 'content_description', 'bounds', 'visible', 'enabled',
          'clickable', 'checkable', 'checked', 'selected', 'editable', 'password',
          'heading', 'range', 'collection', 'collection_item'}
SECRET = re.compile(r'sk-(?:proj-|ws-|[A-Za-z0-9_-]{20})')


class ObservationError(ValueError):
    pass


def require(condition, code='UI_TREE_ERROR'):
    if not condition:
        raise ObservationError(code)


def plain_copy(value):
    """Checks before serialization; never calls repr/default on untrusted objects."""
    stack, count = [(value, 0)], 0
    while stack:
        current, depth = stack.pop(); count += 1
        require(count <= 160000 and depth <= 80, 'WIRE_LIMIT')
        if type(current) is dict:
            require(all(type(key) is str and len(key) <= 128 for key in current), 'INVALID_DTO')
            stack.extend((item, depth + 1) for item in current.values())
        elif type(current) is list:
            require(len(current) <= 4096, 'WIRE_LIMIT')
            stack.extend((item, depth + 1) for item in current)
        else:
            require(current is None or type(current) in (str, bool, int, float), 'INVALID_DTO')
            if type(current) is str: require(len(current) <= 65536, 'WIRE_LIMIT')
            if type(current) in (int, float):
                require((type(current) is int and current.bit_length() <= 128)
                        or (type(current) is float and math.isfinite(current)), 'INVALID_DTO')
    encoded = canonical(value)
    require(len(encoded.encode('utf-8')) <= MAX_WIRE_BYTES, 'WIRE_LIMIT')
    return json.loads(encoded)


def parse_wire(raw):
    require(type(raw) in (str, bytes), 'INVALID_DTO')
    require(len(raw.encode('utf-8') if type(raw) is str else raw) <= MAX_WIRE_BYTES, 'WIRE_LIMIT')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_FIELD'); result[key] = value
        return result
    try:
        return plain_copy(json.loads(raw, object_pairs_hook=pairs,
                                     parse_constant=lambda _: (_ for _ in ()).throw(ObservationError('INVALID_DTO'))))
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as error:
        raise ObservationError('INVALID_DTO') from error


def identifier(value, *, nullable=False):
    return (value is None and nullable) or (type(value) is str and 0 < len(value) <= 240
                                           and not SECRET.search(value))


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _text(value, sensitive, reasons):
    require(value is None or type(value) is str)
    if value is None: return None
    if sensitive or SECRET.search(value): return '[REDACTED]'
    if len(value) > MAX_TEXT:
        reasons.add('TEXT_LIMIT')
    return value[:MAX_TEXT]


def copy_tree(value):
    raw = plain_copy(value)
    require(type(raw) is dict and set(raw) == {'nodes', 'root_readable', 'complete', 'truncated_reasons'})
    require(type(raw['root_readable']) is bool and raw['root_readable'], 'ROOT_UNAVAILABLE')
    require(type(raw['complete']) is bool and type(raw['truncated_reasons']) is list)
    require(all(identifier(reason) for reason in raw['truncated_reasons']))
    require(type(raw['nodes']) is list and 0 < len(raw['nodes']) <= 4096)
    nodes, index, reasons = [], {}, set(raw['truncated_reasons'])
    for node in raw['nodes']:
        require(type(node) is dict and set(node) == FIELDS)
        local, parent = node['node_local_id'], node['parent_local_id']
        require(identifier(local) and identifier(parent, nullable=True) and local not in index, 'BAD_NODE_REFERENCE')
        for key in ('package', 'resource_id', 'class_name', 'role'):
            require(identifier(node[key], nullable=key == 'resource_id'))
        for key in ('visible', 'enabled', 'clickable', 'checkable', 'selected', 'editable', 'password', 'heading'):
            require(type(node[key]) is bool)
        require(node['checked'] is None or type(node['checked']) is bool)
        bounds = node['bounds']
        require(type(bounds) is list and len(bounds) == 4 and all(type(v) is int for v in bounds))
        require(bounds[2] >= bounds[0] and bounds[3] >= bounds[1])
        if node['range'] is not None:
            r = node['range']
            require(type(r) is dict and set(r) == {'min', 'max', 'value', 'kind'})
            require(all(_number(r[k]) for k in ('min', 'max', 'value')) and r['min'] <= r['value'] <= r['max'])
            require(r['kind'] in ('int', 'float', 'percent'))
        for field in ('collection', 'collection_item'):
            item = node[field]
            require(item is None or type(item) is dict)
            if item is not None:
                allowed = {'rows', 'columns', 'hierarchical', 'selection_mode'} if field == 'collection' else {
                    'row_index', 'row_span', 'column_index', 'column_span', 'heading', 'selected'}
                require(set(item) <= allowed)
                require(all(type(v) in (int, bool) and (type(v) is bool or v >= 0) for v in item.values()))
        sensitive = node['password'] or node['editable']
        node['text'] = _text(node['text'], sensitive, reasons)
        node['content_description'] = _text(node['content_description'], sensitive, reasons)
        node['children_local_ids'] = []
        index[local] = node
    roots = [key for key, n in index.items() if n['parent_local_id'] is None]
    require(len(roots) == 1, 'BAD_NODE_REFERENCE')
    depths = {roots[0]: 0}
    for local in index:
        path, cursor = [], local
        while cursor not in depths:
            require(cursor in index and cursor not in path, 'BAD_NODE_REFERENCE')
            path.append(cursor); cursor = index[cursor]['parent_local_id']
        depth = depths[cursor]
        for key in reversed(path):
            depth += 1; depths[key] = depth
    included = set()
    for local, node in index.items():
        if len(nodes) >= MAX_NODES:
            reasons.add('NODE_LIMIT'); continue
        if depths[local] > MAX_DEPTH:
            reasons.add('DEPTH_LIMIT'); continue
        # A bounded slice never exports a dangling parent reference.
        if node['parent_local_id'] is not None and node['parent_local_id'] not in included:
            reasons.add('PARENT_OUTSIDE_SLICE'); continue
        included.add(local); nodes.append(node)
    for node in nodes:
        parent = node['parent_local_id']
        if parent is not None: index[parent]['children_local_ids'].append(node['node_local_id'])
    complete = raw['complete'] and not reasons
    return {'snapshot_id': str(uuid.uuid4()), 'root_readable': True, 'complete': complete,
            'nodes': nodes, 'root_local_id': roots[0], 'truncated_reasons': sorted(reasons),
            'known_scope': 'PUBLIC_TREE_COMPLETE' if complete else 'PUBLIC_TREE_BOUNDED_SLICE',
            'full_digest': digest({'nodes': nodes, 'complete': complete, 'reasons': sorted(reasons)}),
            'execution_authority': False}
