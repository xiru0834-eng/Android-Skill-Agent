"""Archive original materials without inventing a missing learned Flow."""
from pathlib import Path
import uuid
from p34deps import material_io, audit_io, canonical, digest
from knowledge import need, inert_copy, source_ref, KnowledgeLibrary, KnowledgeError


def _load_approved(path, refs, approved_roots):
    allowed = source_ref(path, approved_roots)
    value = audit_io.load(path, refs)
    need(refs[-1] == allowed, 'SOURCE_CHANGED_DURING_ARCHIVE')
    return value


def archive_material(audit_directory, bundle_paths, output_root, *, approved_roots):
    """Explicit evaluator/operator entry. Does not execute, publish or generate."""
    need(type(bundle_paths) in (list, tuple) and 1 <= len(bundle_paths) <= 16, 'SOURCE_REFERENCE_ERROR')
    refs = []; audit_directory = Path(audit_directory)
    request = _load_approved(audit_directory / 'input.json', refs, approved_roots)
    result = _load_approved(audit_directory / 'result.json', refs, approved_roots)
    bundles = [_load_approved(Path(p), refs, approved_roots) for p in bundle_paths]
    # P3.3 rechecks source hashes, P3.2 lineage and original model response.
    review = material_io.inspect_material(audit_directory, bundle_paths)
    need(review['source_unchanged'] is True, 'ORIGINAL_MATERIAL_NOT_VERIFIED')
    raw = audit_io.original_raw(result, audit_directory, request, refs)
    for ref in review['source_refs']:
        source_ref(ref['path'], approved_roots)
        if ref not in refs: refs.append(ref)
    for ref in refs: need(source_ref(ref['path'], approved_roots) == ref, 'SOURCE_CHANGED_DURING_ARCHIVE')
    need(all(type(b) is dict and b.get('kind') == 'LearningBundle' and b.get('execution_authority') is False for b in bundles),
         'LEARNING_MATERIAL_SCHEMA_ERROR')
    archive = inert_copy({'kind': 'P34MaterialArchive', 'schema_version': '1.0',
        'status': review['status'], 'source_mode': 'REAL_ANDROID_SAVED_MATERIAL',
        'model_original': raw, 'original_model_status': review['original_model_status'],
        'human_revisions': [], 'human_revision_status': 'NO_REVISION_RECORD_SUPPLIED',
        'human_participation': [b.get('human_participation') for b in bundles],
        'human_cost': {'actions': None, 'minutes': None},
        'model_cost': {'calls': result['calls'], 'reported_usd': None,
                       'reserved_usd': result.get('reserved_cost_usd')},
        'flow': None, 'flow_status': 'NOT_SAVED_NO_CHECKED_VALIDATED_FLOW', 'binding_states': [],
        'learning_bundles': bundles, 'source_refs': refs, 'environment_versions': [b['environment'] for b in bundles],
        'actual_points': [], 'parameter_domain_verified': False, 'future_reliability_proven': False,
        'failures': [{'code': review['original_model_status'], 'channel': review['original_evidence_channel']}],
        'limitations': ['HISTORICAL_NOT_CURRENT_UI', 'REAL_FLOW_NOT_VALIDATED', 'NO_NATIVE_FLOW_TRANSPORT'],
        'blocking_items': [p['code'] for p in review['pending_items']], 'predecessor_review': review,
        'current_ui_confirmed': False, 'formal_retrievable': False, 'execution_authority': False,
        'available_tools': [], 'new_model_calls': 0, 'new_android_actions': 0})
    directory = Path(output_root) / str(uuid.uuid4()); directory.mkdir(parents=True, exist_ok=False)
    with (directory / 'archive.json').open('x', encoding='utf-8', newline='\n') as stream: stream.write(canonical(archive))
    with (directory / 'complete.json').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(canonical({'format': 'p34_material_archive_v1', 'file': 'archive.json',
                                'sha256': digest(archive), 'execution_authority': False}))
    return directory


def read_archive(directory, *, approved_roots):
    """Digest checked historical readback, not permission or current UI facts."""
    directory = Path(directory); refs = []
    complete = audit_io.load(directory / 'complete.json', refs)
    need(type(complete) is dict and set(complete) == {'format', 'file', 'sha256', 'execution_authority'}
         and complete['format'] == 'p34_material_archive_v1' and complete['file'] == 'archive.json'
         and complete['execution_authority'] is False, 'ARCHIVE_COMPLETION_ERROR')
    value = audit_io.load(directory / 'archive.json', refs)
    need(type(value) is dict and digest(value) == complete['sha256'], 'ARCHIVE_DIGEST_ERROR')
    inert_copy(value)
    need(value.get('kind') == 'P34MaterialArchive' and value.get('schema_version') == '1.0'
         and value.get('formal_retrievable') is False and value.get('execution_authority') is False
         and value.get('current_ui_confirmed') is False and value.get('flow') is None
         and value.get('actual_points') == [] and value.get('available_tools') == [], 'ARCHIVE_SCHEMA_ERROR')
    KnowledgeLibrary._source_shape(value.get('source_refs'))
    for ref in value['source_refs']:
        need(source_ref(ref['path'], approved_roots) == ref, 'ARCHIVE_SOURCE_CHANGED')
    audit_io.unchanged(refs)
    return value
