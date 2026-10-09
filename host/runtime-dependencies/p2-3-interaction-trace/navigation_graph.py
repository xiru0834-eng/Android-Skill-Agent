"""Evidence-derived directed map, read-only BFS; no live actions or inverse synthesis."""
from collections import deque
from p23deps import digest, identifier
from trace_contract import (need, detached, check_target, matches_target,
                            validate_interaction, target_for)

VALID = 'VERIFIED_SIMULATED'


def _same_context(page, expected):
    keys = ('environment', 'host_device_id', 'boot_session_id')
    return all(page.get(k) == expected.get(k) for k in keys)


class NavigationGraph:
    def __init__(self, entity_types):
        need(type(entity_types) is list and 0 < len(entity_types) <= 32, 'INVALID_ENTITY_TYPES')
        self.entity_types = detached(entity_types)
        self._edges = []
        self.revision = 0

    def add_interaction(self, step, before, after):
        step = validate_interaction(step, before, after, self.entity_types)
        if not step['changes']['page_changed'] or step['source'] not in ('HUMAN_DEMONSTRATION', 'AGENT_NAVIGATION'):
            return None
        for existing in self._edges:
            if existing['evidence']['interaction_id'] == step['interaction_id']:
                return detached(existing)
        need(len(self._edges) < 128, 'MAP_CAPACITY')
        status = VALID if step['status'] == 'ARRIVAL_VERIFIED_SIMULATED' else 'OBSERVED_SIMULATED'
        pre, post = step['before']['page'], step['after']['page']
        edge = {
            'edge_id': digest({'interaction': step['interaction_id'], 'from': pre['page_instance_id'],
                               'to': post['page_instance_id']}),
            'status': status, 'source_page': pre, 'target_page': post,
            'action': step['action'], 'public_clues': step['public_clues'],
            'preconditions': target_for(pre) if pre['identity_status'] == 'KNOWN' else None,
            'arrival_condition': step['expected_target'],
            'evidence': {'interaction_id': step['interaction_id'],
                         'before_observation_id': before['observation_id'],
                         'after_observation_id': after['observation_id'],
                         'dispatch_id': step['dispatch']['dispatch_id'],
                         'source': step['source'], 'interaction_status': step['status']},
            'history': [{'status': status, 'reason': 'ACTUAL_OFFLINE_TRACE_NOT_ANDROID'}],
            'evidence_level': 'NOT_REAL_ANDROID_EVIDENCE', 'execution_authority': False}
        self._edges.append(detached(edge))
        self.revision += 1
        return detached(edge)

    def add_hypothesis(self, source_page, target, model_ref):
        target = check_target(target)
        need(type(source_page) is dict and source_page.get('kind') == 'PageEvidence'
             and identifier(model_ref) and target is not None, 'INVALID_HYPOTHESIS')
        need(len(self._edges) < 128, 'MAP_CAPACITY')
        record = {'edge_id': digest({'model_ref': model_ref, 'from': source_page['observation_id'], 'to': target}),
                  'status': 'HYPOTHESIS', 'source_page': detached(source_page), 'target_page': None,
                  'action': None, 'public_clues': None, 'preconditions': None, 'arrival_condition': target,
                  'evidence': {'interaction_id': None, 'model_ref': model_ref},
                  'history': [{'status': 'HYPOTHESIS', 'reason': 'MODEL_PROPOSAL_NOT_TRANSITION'}],
                  'evidence_level': 'UNVERIFIED_MODEL_PROPOSAL', 'execution_authority': False}
        self._edges.append(record)
        self.revision += 1
        return detached(record)

    def invalidate(self, edge_id, reason):
        need(identifier(reason), 'INVALID_INVALIDATION')
        for edge in self._edges:
            if edge['edge_id'] == edge_id:
                edge['status'] = 'INVALIDATED'
                edge['history'].append({'status': 'INVALIDATED', 'reason': reason})
                self.revision += 1
                return detached(edge)
        need(False, 'EDGE_NOT_FOUND')

    def search(self, current_page, target):
        target = check_target(target)
        page = detached(current_page)
        need(type(page) is dict and page.get('kind') == 'PageEvidence', 'INVALID_PAGE')
        result = {'status': 'NO_KNOWN_PATH', 'edges': [], 'map_revision': self.revision,
                  'scope': 'KNOWN_VERIFIED_SIMULATED_GRAPH_ONLY',
                  'claim': 'NO_KNOWN_PATH_IS_NOT_ABSENCE_OF_APP_FUNCTION',
                  'execution_authority': False, 'model_calls': 0}
        if page.get('identity_status') != 'KNOWN':
            result['status'] = 'IDENTITY_UNCONFIRMED'
            return result
        if matches_target(page, target):
            result['status'] = 'ALREADY_AT_TARGET'
            return result
        queue = deque([(page, [])])
        seen = {digest(target_for(page))}
        ordered = sorted(self._edges, key=lambda e: e['edge_id'])
        while queue:
            node, route = queue.popleft()
            for edge in ordered:
                if edge['status'] != VALID or not _same_context(node, edge['source_page']):
                    continue
                if not matches_target(node, edge['preconditions']):
                    continue
                following = edge['target_page']
                path = route + [detached(edge)]
                if matches_target(following, target):
                    result.update(status='FOUND', edges=path)
                    return result
                key = digest(target_for(following))
                if key not in seen:
                    seen.add(key)
                    queue.append((following, path))
        return result

    def snapshot(self):
        return {'kind': 'NavigationMapEvidence', 'schema_version': '1.0',
                'memory_revision': self.revision, 'edges': detached(self._edges),
                'verified_simulated_edges': sum(e['status'] == VALID for e in self._edges),
                'real_verified_edges': 0, 'execution_authority': False,
                'is_live_ui_query': False, 'model_calls': 0}

    def edge(self, edge_id):
        for edge in self._edges:
            if edge['edge_id'] == edge_id:
                return detached(edge)
        need(False, 'EDGE_NOT_FOUND')
