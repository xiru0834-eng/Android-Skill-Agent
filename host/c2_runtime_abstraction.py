"""Evidence-constrained analysis of inert P3.1 proposals, never execution or approval."""
import copy
import hashlib
import re
from p32deps import (bundle_contract, canonical, contracts, digest, p31_draft,
                     p31_request, public_capabilities)
import c2_runtime_request

ROLES = {'REQUIRED_BUSINESS', 'REQUIRED_SUBMISSION', 'PROTECTION', 'VERIFICATION',
         'INCIDENTAL', 'IRRELEVANT', 'UNKNOWN'}
DOCUMENTED_BASES = {'DOCUMENTATION_STATEMENT', 'HUMAN_CONFIRMATION'}
NOTE_KEYS = {'schema_version', 'entity_evidence', 'parameter_groups', 'step_roles',
             'explicit_order', 'conditions', 'assistance'}
NAME = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
CHANNELS = {'UNCLASSIFIED_INPUT', 'SYNTHETIC_PROTOCOL', 'NO_MODEL_CALL', 'REAL_OPENAI_API', 'FAKE_MODEL_PROTOCOL_ONLY'}


class AnalysisError(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise AnalysisError(code)


def exact(value, keys):
    need(type(value) is dict and set(value) == set(keys), 'SUPPLEMENT_CONTRACT_ERROR')


def text(value):
    need(type(value) is str and 1 <= len(value) <= 2000, 'SUPPLEMENT_CONTRACT_ERROR')


def unknown(out, code, description, source_ids=()):
    row = {'code': code, 'description': description, 'source_ids': list(source_ids)}
    if row not in out['unknowns']:
        out['unknowns'].append(row)


def validate_inputs(request, bundles, *, runtime_snapshot=None, original_goal=None):
    # Versioned extension: the trusted snapshot is supplied out-of-band by
    # LearningService. Never trust a profile embedded in model/client JSON.
    return c2_runtime_request.validate_request(request,bundles,runtime_snapshot=runtime_snapshot,original_goal=original_goal)


def validate_notes(notes):
    exact(notes, NOTE_KEYS)
    need(notes['schema_version'] == '1.0', 'SUPPLEMENT_CONTRACT_ERROR')
    for key in ('entity_evidence', 'parameter_groups', 'step_roles', 'explicit_order', 'conditions'):
        need(type(notes[key]) is list and len(notes[key]) <= 128, 'SUPPLEMENT_CONTRACT_ERROR')
    for row in notes['entity_evidence']:
        exact(row, ('entity_input', 'entity_id', 'identity_basis', 'supported_capabilities'))
        need(type(row['entity_input']) is str and NAME.fullmatch(row['entity_input']), 'SUPPLEMENT_CONTRACT_ERROR')
        text(row['entity_id'])
        need(row['identity_basis'] in ('PUBLIC_DOCUMENT', 'HUMAN_CONFIRMATION'), 'IDENTITY_EVIDENCE_UNKNOWN')
        caps = row['supported_capabilities']
        need(type(caps) is list and 1 <= len(caps) <= 8 and all(type(v) is str for v in caps)
             and len(set(caps)) == len(caps), 'SUPPLEMENT_CONTRACT_ERROR')
    for row in notes['parameter_groups']:
        exact(row, ('name', 'paths', 'entity_input', 'property', 'reason', 'domain', 'domain_basis'))
        need(type(row['name']) is str and NAME.fullmatch(row['name']), 'SUPPLEMENT_CONTRACT_ERROR')
        for key in ('entity_input', 'property', 'reason'):
            text(row[key])
        paths = row['paths']
        need(type(paths) is list and 1 <= len(paths) <= 128 and all(type(p) is str and len(p) <= 160 for p in paths)
             and len(set(paths)) == len(paths), 'SUPPLEMENT_CONTRACT_ERROR')
        domain = row['domain']
        need(type(domain) is dict, 'SUPPLEMENT_CONTRACT_ERROR')
        if domain.get('type') == 'integer':
            exact(domain, ('type', 'minimum', 'maximum', 'step', 'unit'))
            need(all(type(domain[k]) is int for k in ('minimum', 'maximum', 'step'))
                 and domain['step'] > 0 and domain['minimum'] <= domain['maximum'], 'PARAMETER_DOMAIN_INVALID')
        elif domain.get('type') == 'enum':
            exact(domain, ('type', 'choices', 'unit'))
            choices = domain['choices']
            need(type(choices) is list and 1 <= len(choices) <= 256 and all(type(v) is str for v in choices)
                 and len(set(choices)) == len(choices), 'PARAMETER_DOMAIN_INVALID')
        else:
            raise AnalysisError('PARAMETER_DOMAIN_UNSUPPORTED')
        need(row['domain_basis'] == 'APPROVED_ENTITY_CAPABILITY', 'PARAMETER_DOMAIN_UNPROVEN')
    for row in notes['step_roles']:
        exact(row, ('step_id', 'role', 'reason'))
        text(row['step_id']); text(row['reason'])
        need(row['role'] in ROLES, 'SUPPLEMENT_CONTRACT_ERROR')
    need(all(type(s) is str for s in notes['explicit_order'])
         and len(set(notes['explicit_order'])) == len(notes['explicit_order']), 'SUPPLEMENT_CONTRACT_ERROR')
    for row in notes['conditions']:
        exact(row, ('kind', 'status', 'description'))
        need(row['kind'] in ('BRANCH', 'PRECONDITION', 'SUBMISSION')
             and row['status'] in ('REQUIRED', 'UNKNOWN', 'NOT_REQUIRED'), 'SUPPLEMENT_CONTRACT_ERROR')
        text(row['description'])
    a = notes['assistance']
    exact(a, ('actor', 'reason', 'elapsed_seconds', 'provided_new_rules', 'provided_new_route'))
    text(a['actor']); text(a['reason'])
    need(type(a['elapsed_seconds']) is int and 0 <= a['elapsed_seconds'] <= 86400
         and type(a['provided_new_rules']) is bool and type(a['provided_new_route']) is bool,
         'SUPPLEMENT_CONTRACT_ERROR')


def occurrences(flow, capabilities):
    by_property = {c['property']: c for c in capabilities['definitions']}
    reads = {s['id']: s['target'] for s in flow['steps'] if s['op'] == 'read'}
    rows = []

    def target_of(value):
        if value['kind'] in ('state', 'initial'):
            return {'entity_input': value['entity_input'], 'property': value['property']}
        return reads.get(value.get('step_id')) if value['kind'] == 'read' else None

    def add(value, path, context, step_id, target):
        if value['kind'] not in ('literal', 'input'):
            return
        prop = target['property'] if target else None
        cap = by_property.get(prop)
        rows.append({'occurrence_id': 'occ.' + digest({'flow': digest(flow), 'path': path})[:24],
                     'path': path, 'value_kind': value['kind'], 'value': value.get('value'),
                     'input_name': value.get('name'), 'context': context, 'step_id': step_id,
                     'entity_input': target['entity_input'] if target else None, 'property': prop,
                     'unit': cap['unit'] if cap else None,
                     'domain': {'global_approved': copy.deepcopy(cap), 'entity_domain': 'UNKNOWN',
                                'demonstration_proves_domain': False}, 'basis': 'CANDIDATE_SYNTAX_NOT_UI_FACT'})

    def predicate(pred, path, context, step_id=None):
        if pred['op'] == 'known':
            add(pred['value'], path + '/value', context, step_id, target_of(pred['value']))
        else:
            add(pred['left'], path + '/left', context, step_id, target_of(pred['right']))
            add(pred['right'], path + '/right', context, step_id, target_of(pred['left']))

    for i, step in enumerate(flow['steps']):
        if step['op'] == 'call':
            cap = next(c for c in capabilities['definitions'] if c['name'] == step['capability'])
            add(step['argument'], f'/steps/{i}/argument', 'BUSINESS_ARGUMENT', step['id'],
                {'entity_input': step['entity_input'], 'property': cap['property']})
        elif step['op'] == 'assert':
            predicate(step['predicate'], f'/steps/{i}/predicate', 'STEP_PREDICATE', step['id'])
    for field in ('preconditions', 'goals'):
        for i, pred in enumerate(flow[field]):
            predicate(pred, f'/{field}/{i}', field.upper())
    return rows


def entity_and_groups(out, flow, notes, source, capabilities):
    entity_inputs = {i['name']: i for i in flow['inputs'] if i['type'] == 'entity'}
    evidence = {}
    for entity in notes['entity_evidence']:
        need(entity['entity_input'] in entity_inputs, 'ENTITY_INPUT_UNKNOWN')
        available = {c['name'] for c in capabilities['entity_capabilities'] if c['entity_id'] == entity['entity_id']}
        need(set(entity['supported_capabilities']) <= available
             and set(entity_inputs[entity['entity_input']]['required_capabilities']) <= set(entity['supported_capabilities']),
             'ENTITY_CAPABILITY_MISMATCH')
        row = dict(entity, source_id=source['source_id'], source_basis=source['basis'],
                   evidence_status='DOCUMENTED_NOT_EXECUTION_VERIFIED')
        previous = next((r for r in out['entity_choice_table'] if r['entity_input'] == entity['entity_input']), None)
        need(previous is None or previous['entity_id'] == entity['entity_id'], 'ENTITY_EVIDENCE_CONFLICT')
        evidence[entity['entity_input']] = entity
        if row not in out['entity_choice_table']:
            out['entity_choice_table'].append(row)
    indexed = {r['path']: r for r in out['occurrences']}
    for group in notes['parameter_groups']:
        need(group['entity_input'] in evidence, 'ENTITY_MAPPING_UNKNOWN')
        need(all(p in indexed for p in group['paths']), 'PARAMETER_PATH_UNKNOWN')
        selected = [indexed[p] for p in group['paths']]
        need(all(r['entity_input'] == group['entity_input'] and r['property'] == group['property'] for r in selected),
             'CROSS_ENTITY_OR_PROPERTY_GROUP')
        need(all(r['context'] != 'PRECONDITIONS' for r in selected),
             'PARAMETER_ROLE_UNSUPPORTED')
        kinds = {r['value_kind'] for r in selected}
        need(len(kinds) == 1, 'PARAMETER_VALUE_KIND_CONFLICT')
        existing = next((i for i in flow['inputs'] if i['name'] == group['name']), None)
        if kinds == {'input'}:
            need(existing is not None and all(r['input_name'] == group['name'] for r in selected), 'PARAMETER_NAME_CONFLICT')
            used = {r['path'] for r in out['occurrences'] if r['input_name'] == group['name']}
            need(used == set(group['paths']), 'PARAMETER_REFERENCE_MAPPING_INCOMPLETE')
        else:
            need(existing is None, 'PARAMETER_GROUP_CONFLICT')
        need(any(r['context'] == 'BUSINESS_ARGUMENT' for r in selected), 'PARAMETER_WITHOUT_BUSINESS_CALL')
        need(all(r['context'] != 'STEP_PREDICATE' or next(s for s in out['fixed_variable_unknown_steps']
             if s['step_id'] == r['step_id'])['role'] == 'VERIFICATION' for r in selected), 'PROTECTION_PARAMETER_FORBIDDEN')
        need(len({canonical(r['value']) for r in selected}) == 1, 'PARAMETER_DEMONSTRATION_CONFLICT')
        cap = next(c for c in capabilities['definitions'] if c['property'] == group['property'])
        entity_id = evidence[group['entity_input']]['entity_id']
        supported = next((c for c in capabilities['entity_capabilities'] if c['entity_id'] == entity_id and c['name'] == cap['name']), None)
        need(supported is not None, 'ENTITY_CAPABILITY_MISMATCH')
        d = supported['domain']
        approved = ({'type': 'integer', 'minimum': d['min'], 'maximum': d['max'], 'step': d['step'], 'unit': supported['unit']}
                    if cap['type'] == 'integer' else {'type': 'enum', 'choices': d['values'], 'unit': supported['unit']})
        stated = copy.deepcopy(group['domain'])
        # This slice accepts the exact approved domain, not silently narrowed/widened or converted domains.
        if stated['type'] == 'enum':
            need(set(stated['choices']) == set(approved['choices']), 'PARAMETER_DOMAIN_MISMATCH')
            stated['choices'] = approved['choices']
        need(stated == approved, 'PARAMETER_DOMAIN_MISMATCH')
        val = selected[0]['value']
        if existing:
            candidate_domain = {k: v for k, v in existing.items() if k not in ('name', 'default_rule')}
            if cap['type'] == 'enum':
                candidate_domain['choices'] = sorted(candidate_domain['choices'])
                equivalent = dict(approved, choices=sorted(approved['choices']))
            else:
                equivalent = approved
            need(candidate_domain == equivalent, 'PARAMETER_DOMAIN_MISMATCH')
        else:
            need((type(val) is int and approved['minimum'] <= val <= approved['maximum']
                  and (val - approved['minimum']) % approved['step'] == 0) if cap['type'] == 'integer'
                 else val in approved['choices'], 'DEMONSTRATION_OUT_OF_DOMAIN')
        occupied = {p for r in out['parameter_source_table'] for p in r['occurrence_paths']}
        need(not occupied.intersection(group['paths']) and group['name'] not in {r['parameter'] for r in out['parameter_source_table']},
             'PARAMETER_GROUP_CONFLICT')
        out['parameter_source_table'].append({'parameter': group['name'], 'occurrence_paths': group['paths'],
            'entity_input': group['entity_input'], 'property': group['property'], 'demonstration_value': val,
            'domain': approved, 'domain_source': 'PINNED_P1_ENTITY_CAPABILITY', 'source_id': source['source_id'],
            'fragment_digest': source['fragment_digest'], 'source_basis': source['basis'], 'reason': group['reason'],
            'value_kind': selected[0]['value_kind'], 'evidence_status': 'DOCUMENTED_NOT_EXECUTION_VERIFIED', 'verified_parameter_values': []})


def analyze(request, raw_draft, bundles, *, input_channel='UNCLASSIFIED_INPUT', runtime_snapshot=None, original_goal=None):
    out = {'kind': 'FlowAbstractionReport', 'schema_version': '1.0', 'status': 'UNCONFIRMED',
           'mode': 'ANALYSIS_ONLY', 'input_channel': input_channel if type(input_channel) is str and input_channel in CHANNELS else 'UNCLASSIFIED_INPUT', 'execution_authority': False,
           'candidate_lifecycle': 'DRAFT_ONLY', 'ready_for_execution': False, 'candidate_flow': None,
           'revised_flow': None, 'occurrences': [], 'parameter_source_table': [], 'entity_choice_table': [],
           'candidate_parameters': [], 'existing_parameter_source_table': [], 'fixed_variable_unknown_steps': [], 'trace_classification': [],
           'assistance': [], 'conditions': [], 'unknowns': [], 'checks': {}, 'model_calls': 0, 'device_actions': 0}
    try:
        need(type(input_channel) is str and input_channel in CHANNELS, 'INPUT_CHANNEL_INVALID')
        validate_inputs(request, bundles, runtime_snapshot=runtime_snapshot, original_goal=original_goal)
        out['input_digest'] = request['input_digest']
        out['material_refs'] = [{'bundle_id': b['bundle_id'], 'digest': digest(b)} for b in bundles]
        for gap in request['knowledge_gaps']:
            unknown(out, gap, 'P3.1 host-computed knowledge gap retained')
        out['trace_classification'] = [dict(t, necessity='UNKNOWN', relevance='NOT_AUTOMATICALLY_REQUIRED')
                                       for t in request['material']['traces']]
        if raw_draft is None:
            out['status'] = 'BLOCKED_NO_CANDIDATE'
            unknown(out, 'ORIGINAL_CANDIDATE_MISSING', 'No original P3.1 proposal; no default Flow supplied')
            return out
        try:
            draft, checks = p31_draft.check_draft(raw_draft, request)
        except p31_draft.ModelFailure as exc:
            out['checks']['candidate_error'] = exc.code
            raise AnalysisError('CANDIDATE_INVALID') from None
        out['checks']['p31'] = checks
        out['candidate_raw_sha256'] = hashlib.sha256(raw_draft.encode()).hexdigest()
        flow = draft['candidate_flow']
        if flow is None:
            out['status'] = 'BLOCKED_NO_CANDIDATE'
            out['unknowns'].extend(draft['uncertainties'])
            return out
        out['candidate_flow'] = copy.deepcopy(flow)
        out['candidate_flow_digest'] = digest(flow)
        out['candidate_parameters'] = copy.deepcopy(draft['parameter_basis'])
        out['unknowns'].extend(draft['uncertainties'])
        for row in flow['unknowns']:
            unknown(out, row['id'], row['description'])
        out['occurrences'] = occurrences(flow, request['allowed_capabilities'])
        for spec in flow['inputs']:
            if spec['type'] == 'entity':
                continue
            paths = [r['path'] for r in out['occurrences'] if r['input_name'] == spec['name']]
            basis = next(r for r in draft['parameter_basis'] if r['parameter'] == spec['name'])
            out['existing_parameter_source_table'].append({'parameter': spec['name'], 'occurrence_paths': paths,
                'declared_domain': {k: v for k, v in spec.items() if k not in ('name', 'default_rule')},
                'source_ids': basis['source_ids'], 'evidence_status': 'CANDIDATE_DECLARATION_ONLY'})
        for step in flow['steps']:
            structural = {'read': 'STATE_READ', 'call': 'BUSINESS_PROPOSAL', 'assert': 'RESULT_CHECK'}[step['op']]
            refs = next(r['source_ids'] for r in draft['step_basis'] if r['step_id'] == step['id'])
            out['fixed_variable_unknown_steps'].append({'step_id': step['id'], 'op': step['op'],
                'structural_role': structural, 'role': 'UNKNOWN', 'necessity_basis': 'UNKNOWN', 'source_ids': refs,
                'reason': 'Recorded/proposed action alone does not prove necessity'})
        declared = []
        seen_sources = set()
        for bundle in bundles:
            for source in bundle['sources']:
                if source['source_id'] in seen_sources:
                    continue
                seen_sources.add(source['source_id'])
                notes = source['fragment'].get('public_flow_notes') if type(source['fragment']) is dict else None
                if notes is None:
                    continue
                if source['basis'] not in DOCUMENTED_BASES:
                    unknown(out, 'UNVERIFIED_SUPPLEMENT', 'Hypothesis or inference is not documentary proof', [source['source_id']])
                    continue
                need(source['source_id'] in flow['evidence_refs'], 'SUPPLEMENT_NOT_CITED')
                validate_notes(notes)
                declared.append((source, notes))
        ids = [s['id'] for s in flow['steps']]
        for source, notes in declared:
            need(all(s in ids for s in notes['explicit_order']), 'ORDER_STEP_UNKNOWN')
            need([s for s in ids if s in notes['explicit_order']] == notes['explicit_order'], 'ORDER_CONFLICT')
            for role in notes['step_roles']:
                need(role['step_id'] in ids, 'ROLE_STEP_UNKNOWN')
                row = next(s for s in out['fixed_variable_unknown_steps'] if s['step_id'] == role['step_id'])
                need(source['source_id'] in row['source_ids'], 'ROLE_SOURCE_NOT_CITED')
                need(row['necessity_basis'] == 'UNKNOWN' or row['role'] == role['role'], 'ROLE_EVIDENCE_CONFLICT')
                row.update(role=role['role'], reason=role['reason'], necessity_basis=source['basis'])
            out['assistance'].append(dict(notes['assistance'], source_id=source['source_id'], source_basis=source['basis']))
            out['conditions'].extend(dict(c, source_id=source['source_id'], evidence_basis=source['basis']) for c in notes['conditions'])
        for source, notes in declared:
            entity_and_groups(out, flow, notes, source, request['allowed_capabilities'])
        if declared:
            out['mode'] = 'ASSISTED'
        grouped = {p for g in out['parameter_source_table'] for p in g['occurrence_paths']}
        if any(o['value_kind'] == 'literal' and o['path'] not in grouped for o in out['occurrences']):
            unknown(out, 'PARAMETER_GROUPING_UNKNOWN', 'Ungrouped literals stay fixed; equal values do not imply a shared parameter')
        proven_entities = {r['entity_input'] for r in out['entity_choice_table']}
        for spec in flow['inputs']:
            if spec['type'] == 'entity' and spec['name'] not in proven_entities:
                unknown(out, 'ENTITY_GENERALIZATION_UNKNOWN', 'No public identity/capability evidence for ' + spec['name'])
        proven_parameters = {r['parameter'] for r in out['parameter_source_table']}
        for row in out['existing_parameter_source_table']:
            if row['parameter'] in proven_parameters:
                row['evidence_status'] = 'DOCUMENTED_NOT_EXECUTION_VERIFIED'
            else:
                unknown(out, 'PARAMETER_DOMAIN_EVIDENCE_UNKNOWN', 'Candidate constraints alone do not prove ' + row['parameter'])
        if not out['conditions']:
            unknown(out, 'CONDITIONS_NOT_ESTABLISHED', 'No new branch, prerequisite or submission rule inferred')
        for c in out['conditions']:
            if c['status'] == 'UNKNOWN':
                unknown(out, c['kind'] + '_UNKNOWN', c['description'], [c['source_id']])
        if any(c['kind'] == 'BRANCH' and c['status'] == 'REQUIRED' for c in out['conditions']):
            out['status'] = 'UNSUPPORTED_BRANCH'
        elif any(c['kind'] in ('SUBMISSION', 'PRECONDITION') and c['status'] == 'REQUIRED' for c in out['conditions']):
            # Documentary requirements cannot be silently inserted into this ordered grammar.
            out['status'] = 'REQUIRES_CONDITION_REVIEW'
        else:
            out['status'] = 'ANALYZED_DRAFT_WITH_UNKNOWNS' if out['unknowns'] else 'ANALYZED_DRAFT'
    except (AnalysisError, p31_request.RequestError, bundle_contract.BundleError) as exc:
        out['status'] = str(exc) if re.fullmatch(r'[A-Z_]+', str(exc)) else 'INPUT_CONTRACT_ERROR'
    except (KeyError, TypeError, ValueError, StopIteration, RecursionError):
        out['status'] = 'INPUT_CONTRACT_ERROR'
    # Invalid evidence may be inspected, but cannot leave a partly accepted parameter map behind.
    if out['status'] not in ('ANALYZED_DRAFT', 'ANALYZED_DRAFT_WITH_UNKNOWNS', 'UNSUPPORTED_BRANCH',
                             'REQUIRES_CONDITION_REVIEW', 'BLOCKED_NO_CANDIDATE'):
        out['parameter_source_table'] = []
        out['entity_choice_table'] = []
    return out
