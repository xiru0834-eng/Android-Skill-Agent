"""Public-tree page evidence and auxiliary indexes, never executable bindings."""
import re
import unicodedata

from observation_capture import VALID
from observation_contract import validate_observation
from observation_tree import identifier, plain_copy, require
from p22deps import digest


def _label(value):
    return ' '.join(unicodedata.normalize('NFKC', value).split())


def _entity(label, types):
    # Prefixes interpret a public heading, not a hidden entity catalog/mapping.
    aliases = {'room': ['Room', '房间'], 'light': ['Light', 'Lamp', '灯'],
               'ac': ['Air Conditioner', '空调']}
    for entity_type in types:
        for prefix in aliases.get(entity_type, [entity_type]):
            # English prefix collisions (Roommate) are not an entity label.
            # A compact numeric identity (Room101) is allowed, but is never stripped.
            match = re.fullmatch(re.escape(prefix) + r'(?:[\s:#：-]+(\S.{0,100})|(\d.{0,100}))', label, re.I)
            if match:
                suffix = (match.group(1) or match.group(2)).strip()
                return {'type': entity_type, 'label': label,
                        'entity_key': digest({'type': entity_type, 'public_identity': suffix.casefold()}),
                        'identity_basis': 'PUBLIC_HEADING_LABEL_NOT_CATALOG_ENTITY_ID'}
    return None


def derive_page(observation, *, entity_types, model_proposals=None):
    obs = validate_observation(observation)
    require(type(entity_types) is list and 0 < len(entity_types) <= 32
            and all(identifier(t) for t in entity_types), 'INVALID_ENTITY_TYPES')
    proposals = plain_copy(model_proposals or [])
    require(type(proposals) is list and len(proposals) <= 32, 'INVALID_PROPOSALS')
    result = {'kind': 'PageEvidence', 'schema_version': '1.0', 'observation_id': obs['observation_id'],
              'environment': obs.get('environment'), 'host_device_id': obs.get('host_device_id'),
              'boot_session_id': obs.get('boot_session_id'), 'template_id': None,
              'page_instance_id': None, 'view_slice_id': None, 'identity_status': 'UNAVAILABLE',
              'entities': [], 'dynamic_state': [], 'navigation_context': obs.get('navigation_context'),
              'regions': [], 'elements': [], 'known_scope': obs.get('known_scope'),
              'model_proposals': [{'status': 'HYPOTHESIS', 'proposal': p,
                                  'evidence_source': 'UNVERIFIED_MODEL_PROPOSAL'} for p in proposals],
              'evidence_status': 'OFFLINE_TREE_EVIDENCE', 'execution_authority': False}
    if obs.get('capture_status') not in VALID or obs.get('tree') is None:
        return result
    tree = obs['tree']; nodes = tree['nodes']; index = {n['node_local_id']: n for n in nodes}
    headings = []
    for n in nodes:
        text = n['text'] or n['content_description']
        if n['visible'] and n['heading'] and text and text != '[REDACTED]':
            entity = _entity(_label(text), entity_types)
            if entity:
                entity.update(node_local_id=n['node_local_id'], region_anchor=n['parent_local_id'] or n['node_local_id'],
                              evidence_ref={'observation_id': obs['observation_id'], 'node_local_id': n['node_local_id'],
                                            'fields': ['heading', 'text', 'content_description', 'parent_local_id']})
                headings.append(entity)
    keys = [e['entity_key'] for e in headings]
    identity = 'KNOWN' if headings and len(keys) == len(set(keys)) else ('AMBIGUOUS' if headings else 'UNKNOWN')
    heading_by_local = {e['node_local_id']: e for e in headings}
    # Structural hash excludes typed values, checked/selected state, bounds and viewport.
    # Non-entity headings retain their digits; no global digit stripping is used.
    positions = {n['node_local_id']: i for i, n in enumerate(nodes)}
    shape = [{'parent': positions.get(n['parent_local_id']), 'role': n['role'], 'class': n['class_name'],
              'resource_id': n['resource_id'], 'range_kind': n['range']['kind'] if n['range'] else None,
              'heading': ('ENTITY:' + heading_by_local[n['node_local_id']]['type']) if n['node_local_id'] in heading_by_local
                         else _label(n['text'] or n['content_description'] or '') if n['heading'] else None}
             for n in nodes]
    template = digest({'public_shape': shape})
    nav = obs['navigation_context']
    semantic_context = {k: nav[k] for k in ('tab', 'popup', 'expanded', 'entry', 'page_hint')}
    instance_basis = {'environment': obs['environment'], 'host_device_id': obs['host_device_id'],
                      'template_id': template, 'entities': sorted(set(keys)), 'context': semantic_context}
    if identity != 'KNOWN': instance_basis['unconfirmed_observation'] = obs['observation_id']
    instance = digest(instance_basis)
    anchors = {e['region_anchor'] for e in headings}
    if not anchors: anchors = {tree['root_local_id']}
    regions = {a: {'region_id': digest({'page': instance, 'anchor': a}), 'anchor_node_local_id': a,
                   'label': ' / '.join(e['label'] for e in headings if e['region_anchor'] == a) or None,
                   'grouping_status': 'PUBLIC_ANCESTOR_EVIDENCE', 'element_refs': [],
                   'evidence_ref': {'observation_id': obs['observation_id'], 'node_local_id': a}}
               for a in anchors}
    elements, states = [], []
    for n in nodes:
        local, cursor, anchor = n['node_local_id'], n['node_local_id'], None
        while cursor is not None:
            if cursor in anchors:
                anchor = cursor; break
            cursor = index[cursor]['parent_local_id']
        owners = [e for e in headings if e['region_anchor'] == anchor]
        owner = owners[0]['entity_key'] if identity == 'KNOWN' and len(owners) == 1 else None
        region = regions[anchor]['region_id'] if anchor is not None else None
        evidence = {'observation_id': obs['observation_id'], 'node_local_id': local}
        element = {'element_id': digest(evidence), 'node_local_id': local, 'entity_key': owner,
                   'region_id': region, 'role': n['role'], 'class_name': n['class_name'],
                   'resource_id': n['resource_id'], 'text': n['text'], 'content_description': n['content_description'],
                   'bounds': n['bounds'], 'visible': n['visible'], 'enabled': n['enabled'],
                   'clickable': n['clickable'], 'checkable': n['checkable'], 'range': n['range'],
                   'evidence_ref': evidence, 'evidence_status': 'PUBLIC_TREE_FACT', 'execution_authority': False}
        elements.append(element)
        if anchor is not None: regions[anchor]['element_refs'].append(element['element_id'])
        if n['visible']:
            if n['checked'] is not None:
                states.append({'field': 'checked', 'value': n['checked'], 'entity_key': owner, 'evidence_ref': evidence})
            if n['selected']:
                states.append({'field': 'selected', 'value': True, 'entity_key': owner, 'evidence_ref': evidence})
            if n['range'] is not None:
                states.append({'field': 'range.value', 'value': n['range']['value'], 'entity_key': owner, 'evidence_ref': evidence})
    result.update(template_id=template, page_instance_id=instance, identity_status=identity,
                  entities=headings, dynamic_state=states, regions=list(regions.values()), elements=elements,
                  view_slice_id=digest({'page': instance, 'slice': nav['visible_slice'],
                                        'visible_shape': [(e['role'], e['resource_id'], e['bounds']) for e in elements if e['visible']]}),
                  navigation_context_source='CAPTURE_PORT_CONTEXT_NOT_INDEPENDENT_ENTITY_PROOF')
    return plain_copy(result)


def search_elements(page, *, role=None, text=None, preferred_region_id=None, entity_key=None, limit=100):
    value = plain_copy(page)
    require(type(value) is dict and value.get('kind') == 'PageEvidence'
            and value.get('execution_authority') is False, 'INVALID_PAGE')
    require(type(limit) is int and 0 < limit <= 100, 'INVALID_LIMIT')
    for item in (role, text, preferred_region_id, entity_key):
        require(identifier(item, nullable=True), 'INVALID_QUERY')
    items = [e for e in value['elements'] if e['visible']
             and (role is None or e['role'] == role) and (entity_key is None or e['entity_key'] == entity_key)
             and (text is None or text.casefold() in (e['text'] or e['content_description'] or '').casefold())]
    # A region only ranks results. Missing/incorrect grouping never removes a whole-page candidate.
    items.sort(key=lambda e: (e['region_id'] != preferred_region_id, e['element_id']))
    total = len(items)
    return {'status': 'NOT_FOUND' if not total else 'CANDIDATES' if total == 1 else 'AMBIGUOUS',
            'observation_id': value['observation_id'], 'items': items[:limit], 'candidate_count': total,
            'truncated': total > limit, 'search_scope': 'RECORDED_OBSERVATION_VISIBLE_ONLY', 'is_live_ui_query': False,
            'region_policy': 'RANK_WITH_WHOLE_PAGE_FALLBACK', 'execution_authority': False}
