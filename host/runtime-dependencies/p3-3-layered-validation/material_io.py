"""Read original P3.1 receipts; append new inert P3.3 audits without editing sources."""
import hashlib
from pathlib import Path
import uuid
from p33deps import audit_io, canonical, digest
from layered_validation import review_original


def inspect_material(audit_directory, bundle_paths, *, package_path=None, task_path=None):
    predecessor = audit_io.inspect_original(audit_directory, bundle_paths)
    out = {'kind': 'P33MaterialReview', 'schema_version': '1.0', 'status': predecessor['status'],
           'execution_authority': False, 'ready_for_device_execution': False,
           'device_execution_verified': False, 'model_calls': 0, 'device_actions': 0,
           'evidence_channel': 'HISTORICAL_SAVED_MATERIAL_READ_ONLY',
           'original_model_status': predecessor.get('original_model_status'),
           'original_model_calls': predecessor.get('original_model_calls'),
           'original_evidence_channel': predecessor.get('original_evidence_channel'),
           'provenance_assurance': 'LOCAL_AUDIT_HASH_CHAIN_NOT_REMOTE_ATTESTATION',
           'source_refs': predecessor.get('source_refs', []),
           'source_unchanged': predecessor.get('source_unchanged', False),
           'layers': {k: {'status': 'NOT_TESTED'} for k in ('format', 'content', 'authorization')},
           'compiled_plan': None, 'pending_items': []}
    if predecessor['status'] == 'BLOCKED_NO_CANDIDATE':
        out['pending_items'] = [{'code': 'REAL_CANDIDATE_MISSING'}, {'code': 'ANDROID_FLOW_BRIDGE_NOT_CONNECTED'}]
        return out
    if predecessor.get('revised_flow') is None:
        out['pending_items'] = predecessor.get('unknowns', [])
        return out
    if package_path is None or task_path is None:
        out.update(status='BLOCKED_EXECUTION_CONTEXT_MISSING', pending_items=[{'code': 'EXPLICIT_PACKAGE_AND_TASK_REQUIRED'}])
        return out
    try:
        refs = out['source_refs']
        directory = Path(audit_directory)
        request = audit_io.load(directory / 'input.json', refs)
        result = audit_io.load(directory / 'result.json', refs)
        bundles = [audit_io.load(path, refs) for path in bundle_paths]
        raw = audit_io.original_raw(result, directory, request, refs)
        package = audit_io.load(package_path, refs); task = audit_io.load(task_path, refs)
        reviewed = review_original(request, raw, bundles, package, task)
        for key in ('status', 'layers', 'compiled_plan', 'pending_items'):
            out[key] = reviewed[key]
        audit_io.unchanged(refs)
        out['source_unchanged'] = True
    except (audit_io.AuditError, OSError, ValueError, TypeError, KeyError, RecursionError):
        out.update(status='AUDIT_INPUT_INVALID', source_unchanged=False, compiled_plan=None,
                   layers={k: {'status': 'NOT_TESTED'} for k in ('format', 'content', 'authorization')})
    return out


def save_report(root, report):
    directory = Path(root) / str(uuid.uuid4())
    directory.mkdir(parents=True, exist_ok=False)
    artifacts = {'report.json': report, 'layer-receipts.json': report['layers'],
                 'source-refs.json': report.get('source_refs', []), 'pending-items.json': report['pending_items']}
    hashes = []
    for name, value in artifacts.items():
        content = canonical(value)
        with (directory / name).open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
        hashes.append({'file': name, 'sha256': hashlib.sha256(content.encode()).hexdigest()})
    with (directory / 'complete.json').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(canonical({'artifacts': hashes, 'report_digest': digest(report), 'execution_authority': False}))
    return directory


def read_saved(directory):
    """Integrity readback of an audit, never a permission grant or current UI state."""
    directory = Path(directory); refs = []
    complete = audit_io.load(directory / 'complete.json', refs)
    expected = {'report.json', 'layer-receipts.json', 'source-refs.json', 'pending-items.json'}
    audit_io.need(type(complete) is dict and complete.get('execution_authority') is False
                  and type(complete.get('artifacts')) is list, 'AUDIT_OUTPUT_INVALID')
    rows = complete['artifacts']
    audit_io.need(len(rows) == len(expected) and all(type(r) is dict and set(r) == {'file', 'sha256'} for r in rows),
                  'AUDIT_OUTPUT_INVALID')
    audit_io.need({r['file'] for r in rows} == expected, 'AUDIT_OUTPUT_INVALID')
    values = {}
    for row in rows:
        value = audit_io.load(directory / row['file'], refs)
        audit_io.need(refs[-1]['sha256'] == row['sha256'], 'AUDIT_OUTPUT_DIGEST_MISMATCH')
        values[row['file']] = value
    report = values['report.json']
    audit_io.need(type(report) is dict and report.get('kind') == 'P33MaterialReview'
                  and report.get('schema_version') == '1.0', 'AUDIT_OUTPUT_INVALID')
    audit_io.need(digest(report) == complete.get('report_digest') and report.get('execution_authority') is False
                  and report.get('ready_for_device_execution') is False, 'AUDIT_OUTPUT_INVALID')
    audit_io.need(type(report.get('layers')) is dict and set(report['layers']) == {'format', 'content', 'authorization'}
                  and type(report.get('pending_items')) is list, 'AUDIT_OUTPUT_INVALID')
    audit_io.need(values['layer-receipts.json'] == report['layers']
                  and values['source-refs.json'] == report.get('source_refs', [])
                  and values['pending-items.json'] == report['pending_items'], 'AUDIT_OUTPUT_INVALID')
    audit_io.unchanged(refs)
    return report
