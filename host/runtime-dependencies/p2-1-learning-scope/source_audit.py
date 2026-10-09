"""Explicit local historical material audit, not observe or current UI learning."""
import hashlib
from pathlib import Path

from learning_scope import (DOMAINS, ID, TEXT, MaterialReceipt, ScopeError, bounded_document,
                            contracts, need, validate_scope)

BASE = Path(__file__).resolve().parent


def load_catalog():
    return contracts.parse_document((BASE / 'source-catalog.json').read_bytes())['sources']


def audit_file(spec):
    # spec comes from trusted local catalog/caller, NEVER scope.evidence_ref.
    need(type(spec) is dict and set(spec) == {'source_id', 'path', 'sha256', 'domain'}, 'SOURCE_SPEC_ERROR')
    contracts._shape(spec['source_id'], ID)
    need(spec['domain'] in DOMAINS and type(spec['path']) is str, 'SOURCE_SPEC_ERROR')
    try:
        path = Path(spec['path'])
        need(not path.is_symlink() and path.is_file(), 'MATERIAL_UNAVAILABLE')
        need(path.stat().st_size <= 65536, 'MATERIAL_INPUT_LIMIT')
        with path.open('rb') as handle:
            raw = handle.read(65537)
    except OSError:
        raise ScopeError('MATERIAL_UNAVAILABLE') from None
    need(len(raw) <= 65536, 'MATERIAL_INPUT_LIMIT')
    actual_digest = hashlib.sha256(raw).hexdigest()
    need(actual_digest == spec['sha256'], 'MATERIAL_DIGEST_MISMATCH')
    trace = bounded_document(raw)
    need(type(trace) is dict and trace.get('kind') == 'WORKFLOW_TRACE'
         and type(trace.get('version')) is int and trace['version'] == 2, 'MATERIAL_FORMAT_ERROR')
    for field in ('traceId', 'appPackage'):
        contracts._shape(trace.get(field), ID)
    for field in ('appVersion', 'goal'):
        contracts._shape(trace.get(field), TEXT)
    need(trace.get('source') in ('AUTOMATED', 'HUMAN_DECLARED'), 'MATERIAL_SOURCE_UNKNOWN')
    need(type(trace.get('steps')) is list and len(trace['steps']) <= 128, 'MATERIAL_FORMAT_ERROR')
    states = [trace.get('initial'), trace.get('final')]
    for step in trace['steps']:
        need(type(step) is dict, 'MATERIAL_FORMAT_ERROR')
        states.extend((step.get('before'), step.get('after')))
    pages = set()
    for state in states:
        need(type(state) is dict, 'MATERIAL_FORMAT_ERROR')
        contracts._shape(state.get('page'), ID)
        pages.add(state['page'])
    source = {'source_id': spec['source_id'], 'mode': 'DEMONSTRATION_ASSISTED',
              'actor': trace['source'], 'channel': 'HISTORICAL_ANDROID_TRACE',
              'evidence_ref': spec['path'], 'sha256': actual_digest,
              'origin': {'domain': spec['domain'], 'app_package': trace['appPackage'], 'app_build': trace['appVersion']}}
    return {'source': source, 'goal': trace['goal'], 'trace_id': trace['traceId'],
            'known_start_page': trace['initial']['page'], 'observed_pages': sorted(pages),
            'step_count': len(trace['steps']), 'capture_end': trace.get('end'),
            'has_capture_error': bool(trace.get('error')), 'execution_authority': False,
            'evidence_scope': 'HISTORICAL_FILE_NOT_CURRENT_UI_OR_LEARNED_SKILL'}


def receipt_for(audit):
    source = audit['source']
    return MaterialReceipt(source['source_id'], source['sha256'], source['origin']['domain'])


def historical_scope(audit):
    source = audit['source']
    return validate_scope({
        'kind': 'LearningScope', 'schema_version': '1.0', 'scope_id': 'learn.historical.' + audit['trace_id'],
        'target': {**{key: source['origin'][key] for key in ('app_package', 'app_build', 'domain')},
                   'environment_id': 'env.historical_trace', 'ui_revision': None},
        'task': {'goal': audit['goal'], 'entity_types': [],  # Trace does not prove a typed entity catalog.
                 'known_start_page': audit['known_start_page'], 'origin_source_ids': [source['source_id']]},
        'allowed_pages': audit['observed_pages'], 'modes': [source['mode']], 'sources': [source],
        'requested_permissions': {'observe': False, 'navigation': [], 'business_writes': []},
        'authorization_refs': [],
        'budgets': {'max_time_ms': 5000, 'max_observations': 0, 'max_actions': 0,
                    'max_model_requests': 0, 'max_storage_bytes': 65536},
    })
