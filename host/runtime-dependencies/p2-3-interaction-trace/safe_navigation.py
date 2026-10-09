"""Current public candidates plus explicit handler audits; never a route oracle."""
from p23deps import identifier, digest, VALID
from trace_contract import need, detached, observation, KINDS


class SafetyPolicy:
    def __init__(self, rules):
        value = detached(rules)
        need(type(value) is list and len(value) <= 128, 'INVALID_SAFETY_POLICY')
        ids = set()
        for rule in value:
            need(type(rule) is dict and set(rule) == {
                'rule_id', 'kind', 'selector', 'effect', 'handler_evidence', 'review_cost_ms'},
                'INVALID_SAFETY_POLICY')
            need(identifier(rule['rule_id']) and rule['rule_id'] not in ids
                 and rule['kind'] in KINDS and rule['effect'] in ('NO_BUSINESS_WRITE', 'BUSINESS_WRITE', 'UNKNOWN')
                 and identifier(rule['handler_evidence']), 'INVALID_SAFETY_POLICY')
            selector = rule['selector']
            need(type(selector) is dict and set(selector) == {'resource_id', 'role'}
                 and all(identifier(v) for v in selector.values()), 'INVALID_SELECTOR')
            cost = rule['review_cost_ms']
            need(cost is None or type(cost) is int and 0 <= cost <= 3600000, 'INVALID_COST')
            ids.add(rule['rule_id'])
        self._rules = value
        self.digest = digest(value)

    def snapshot(self):
        amounts = [r['review_cost_ms'] for r in self._rules]
        return {'rules': detached(self._rules), 'policy_hash': self.digest,
                'preconfiguration_cost': {'category': 'PRECONFIGURATION', 'actor': 'HUMAN',
                    'unit': 'ms', 'known_sum_ms': sum(v for v in amounts if v is not None),
                    'known_total_ms': sum(amounts) if all(v is not None for v in amounts) else None,
                    'unmeasured_rules': sum(v is None for v in amounts)},
                'assurance': 'DECLARED_HANDLER_AUDIT_FIXTURE_NOT_NATIVE_CERTIFICATION',
                'execution_authority': False}

    def candidates(self, value):
        obs = observation(value)
        if obs['capture_status'] not in VALID:
            return {'status': 'OBSERVATION_UNAVAILABLE', 'items': [], 'rejected': [],
                    'observation_id': obs['observation_id'], 'execution_authority': False}
        nodes = obs['tree']['nodes']
        items, rejected = [], []
        ambiguity = False
        for rule in self._rules:
            matches = [n for n in nodes if n['visible'] and n['enabled']
                       and all(n[k] == v for k, v in rule['selector'].items())]
            if len(matches) > 1:
                rejected.append({'rule_id': rule['rule_id'], 'reason': 'RESOLUTION_AMBIGUOUS',
                                 'node_local_ids': [n['node_local_id'] for n in matches]})
                ambiguity = True
                continue
            if not matches:
                continue
            node = matches[0]
            safe_shape = not node['checkable'] and not node['editable'] and node['range'] is None
            action_shape = (node['clickable'] and node['role'] == 'button') if rule['kind'] in ('CLICK', 'BACK') \
                           else node['role'] == 'container'
            if rule['effect'] != 'NO_BUSINESS_WRITE' or not safe_shape or not action_shape:
                rejected.append({'rule_id': rule['rule_id'], 'reason': 'UNSAFE_OR_UNKNOWN_EFFECT',
                                 'node_local_ids': [node['node_local_id']]})
                continue
            candidate = {'observation_id': obs['observation_id'], 'node_local_id': node['node_local_id'],
                         'kind': rule['kind'], 'rule_id': rule['rule_id'], 'policy_hash': self.digest,
                         'selector': rule['selector'],
                         'semantic_target': node['text'] or node['content_description'] or rule['kind'],
                         'handler_evidence': rule['handler_evidence'], 'execution_authority': False}
            candidate['candidate_id'] = digest(candidate)
            items.append(candidate)
        audited = {n for item in items for n in (item['node_local_id'],)}
        rejected_nodes = {n for item in rejected for n in item['node_local_ids']}
        for node in nodes:
            if node['visible'] and node['enabled'] and node['clickable'] \
                    and node['node_local_id'] not in audited | rejected_nodes:
                rejected.append({'rule_id': None, 'reason': 'HANDLER_NOT_AUDITED',
                                 'node_local_ids': [node['node_local_id']]})
        return detached({'status': 'AMBIGUOUS' if ambiguity else 'CANDIDATES' if items else 'NO_SAFE_CANDIDATES',
                         'observation_id': obs['observation_id'], 'items': sorted(items, key=lambda x: x['candidate_id']),
                         'rejected': rejected, 'execution_authority': False})
