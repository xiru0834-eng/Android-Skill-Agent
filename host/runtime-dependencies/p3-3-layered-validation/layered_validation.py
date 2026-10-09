"""Three inert review layers. No device calls, approval minting or publication."""
import copy
from p33deps import compiler, environment, revision, records, digest


def format_layer(flow, package, task, profile=None):
    """The entire existing P1 compiler runs before a port can be accessed."""
    try:
        plan = compiler.compile_flow(flow, package, task, profile)
        return {'status': 'PASS', 'code': 'WHOLE_PLAN_COMPILED',
                'plan_hash': digest(plan.to_dict()), 'execution_authority': False}, plan
    except compiler.CompileError as exc:
        return dict(exc.receipt(), status='FAIL'), None


def real_execution_gate(plan, authority, port):
    # This is not a second approval mechanism. P1.4 has no native Flow transport.
    # A caller-supplied channel/connected flag cannot change that implementation fact.
    code = 'ANDROID_FLOW_BRIDGE_NOT_CONNECTED'
    if (type(authority) is not records.ValidationAuthority or authority.confirmed is not True or
        type(authority.version_key) is not str or not 0 < len(authority.version_key) <= 256 or
        type(authority.operator_id) is not str or not 0 < len(authority.operator_id) <= 128):
        code = 'VALIDATION_AUTHORITY_REQUIRED'
    return {'status': 'BLOCKED', 'code': code, 'execution_authority': False,
            'device_execution_verified': False, 'ui_action_count': 0,
            'required_checks': ['REAL_CANDIDATE', 'CONTENT_EVIDENCE', 'NATIVE_FLOW_TRANSPORT',
                                'CURRENT_LOCATOR_AND_OBSERVATION', 'EXISTING_LOCAL_TASK_POLICY']}


def review_original(request, raw_draft, bundles, package, task, profile=None):
    """Reconstruct P3.2 from original material; never accept a model's PASS flag."""
    out = {'kind': 'LayeredFlowReview', 'schema_version': '1.0',
           'status': 'BLOCKED_NO_CANDIDATE', 'compiled_plan': None,
           'execution_authority': False, 'ready_for_device_execution': False,
           'device_execution_verified': False, 'pending_items': [],
           'layers': {name: {'status': 'NOT_TESTED'} for name in ('format', 'content', 'authorization')}}
    if raw_draft is None:
        out['pending_items'].append({'code': 'REAL_CANDIDATE_MISSING'})
        return out
    analyzed = revision.propose_parameterization(request, raw_draft, bundles)
    out['source_analysis_status'] = analyzed['status']
    flow = analyzed.get('revised_flow')
    if flow is None:
        # No evidence-supported parameter revision is available. Do not silently
        # execute the demonstration literal or fill default package/task values.
        out['status'] = analyzed['status']
        out['pending_items'] = copy.deepcopy(analyzed.get('unknowns', []))
        return out
    receipt, plan = format_layer(flow, package, task, profile)
    out['layers']['format'] = receipt
    if plan is None:
        out['status'] = 'FORMAT_REJECTED'
        return out
    data = plan.to_dict()
    actual_profile = (profile or environment.audited_room_profile()).to_dict()
    pending = copy.deepcopy(analyzed.get('unknowns', []))
    pending.extend({'code': 'FLOW_BLOCKING_UNKNOWN', 'detail': copy.deepcopy(row)}
                   for row in data['blocking_unknowns'])
    for entity_source in analyzed.get('entity_choice_table', []):
        resolved_entity = task['inputs'].get(entity_source['entity_input'])
        if resolved_entity != {'entity_id': entity_source['entity_id']}:
            pending.append({'code': 'ENTITY_EVIDENCE_MISMATCH', 'entity_input': entity_source['entity_input'],
                            'documented_entity': entity_source['entity_id'], 'task_entity': copy.deepcopy(resolved_entity),
                            'source_id': entity_source['source_id']})
    targets = []
    for step in data['steps']:
        if step['op'] != 'CALL':
            continue
        binding = actual_profile['targets'][step['target_key']]
        targets.append({'step_id': step['id'], 'entity_id': step['entity_id'],
                        'property': step['target_key'].split('.', 1)[1], 'skill': step['skill'],
                        'domain': copy.deepcopy(binding['domain']), 'unit': binding['unit'],
                        'controller': binding['controller'], 'reader': binding['reader'],
                        'submission': binding['submission'], 'verifier': binding['verifier'],
                        'capability_basis': 'PINNED_SOURCE_NOT_LIVE_DEVICE',
                        'current_ui_verified': False, 'parameter_domain_verified': False})
    pending.extend([
        {'code': 'BINDING_NOT_INDEPENDENTLY_VERIFIED',
         'detail': 'A Binding ID or documentary claim does not prove a current unique locator.'},
        {'code': 'CURRENT_OBSERVATION_REQUIRED'},
        {'code': 'ANDROID_FLOW_BRIDGE_NOT_CONNECTED'},
        {'code': 'LOCAL_TASK_AUTHORIZATION_REQUIRED'},
    ])
    # Keep excluded/unknown steps and their reasons. Review never prunes the Flow.
    out.update(status='PENDING_CONFIRMATION', compiled_plan=data, pending_items=pending)
    out['layers']['content'] = {
        'status': 'PENDING_CONFIRMATION', 'targets': targets,
        'parameter_sources': copy.deepcopy(analyzed.get('parameter_source_table', [])),
        'entity_sources': copy.deepcopy(analyzed.get('entity_choice_table', [])),
        'steps': copy.deepcopy(analyzed.get('fixed_variable_unknown_steps', [])),
        'conditions': copy.deepcopy(analyzed.get('conditions', [])),
        'preconditions': copy.deepcopy(data['preconditions']),
        'allowed_writes': copy.deepcopy(data['actual_write_set']),
        'must_preserve': copy.deepcopy(data['must_preserve']),
        'preserve_unmentioned': copy.deepcopy(data['preserve_unmentioned']),
        'verification': 'NOT_TESTED', 'model_consensus_is_evidence': False,
    }
    out['layers']['authorization'] = real_execution_gate(plan, None, None)
    return out
