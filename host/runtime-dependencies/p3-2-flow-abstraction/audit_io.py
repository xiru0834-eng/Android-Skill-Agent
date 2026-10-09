"""Bounded original-receipt loading and append-only P3.2 output. No model/device clients."""
import hashlib
import json
from pathlib import Path
import uuid
from p32deps import canonical, p31_draft, digest
from revision import propose_parameterization

MAX_AUDIT_BYTES = 1048576
CHANNELS = {'NO_MODEL_CALL', 'FAKE_MODEL_PROTOCOL_ONLY', 'REAL_OPENAI_API'}


class AuditError(ValueError):
    pass


def need(ok, code):
    if not ok:
        raise AuditError(code)


def unique_object(pairs):
    obj = {}
    for key, value in pairs:
        need(key not in obj, 'AUDIT_INPUT_INVALID')
        obj[key] = value
    return obj


def load(path, refs):
    with Path(path).open('rb') as stream:
        raw = stream.read(MAX_AUDIT_BYTES + 1)
    need(len(raw) <= MAX_AUDIT_BYTES, 'AUDIT_INPUT_SIZE_LIMIT')
    refs.append({'path': str(Path(path).resolve()), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(AuditError('AUDIT_INPUT_INVALID')))
    except (UnicodeError, json.JSONDecodeError, RecursionError):
        raise AuditError('AUDIT_INPUT_INVALID') from None


def original_raw(result, directory, request, refs):
    need(type(result) is dict and type(result.get('calls')) is int and 0 <= result['calls'] <= 20,
         'P31_RECEIPT_INCONSISTENT')
    need(result.get('execution_authority') is False and result.get('ready_for_device_execution') is False
         and result.get('evidence_channel') in CHANNELS, 'P31_RECEIPT_INCONSISTENT')
    if result['calls'] == 0:
        need(result.get('candidate_flow') is None and result['evidence_channel'] == 'NO_MODEL_CALL',
             'P31_RECEIPT_INCONSISTENT')
        return None
    need(result['evidence_channel'] != 'NO_MODEL_CALL', 'P31_RECEIPT_INCONSISTENT')
    success = result.get('status') in ('DRAFT_ONLY', 'DRAFT_WITH_KNOWLEDGE_GAPS', 'KNOWLEDGE_GAP')
    if not success:
        need(result.get('candidate_flow') is None, 'P31_RECEIPT_INCONSISTENT')
        return None
    response = load(directory / f"{result['calls']:02d}-response.json", refs)
    need(type(response) is dict and type(response.get('raw_redacted')) is str
         and response.get('redaction_applied') is False and response.get('finish_reason') == 'stop'
         and response.get('refusal') is False, 'P31_RECEIPT_INCONSISTENT')
    raw = response['raw_redacted']
    need(hashlib.sha256(raw.encode()).hexdigest() == response.get('raw_sha256'), 'P31_RECEIPT_INCONSISTENT')
    draft, _ = p31_draft.check_draft(raw, request)
    need(all(result.get(k) == v for k, v in draft.items() if k != 'status'), 'P31_RECEIPT_INCONSISTENT')
    return raw


def unchanged(refs):
    for ref in refs:
        with Path(ref['path']).open('rb') as stream:
            raw = stream.read(MAX_AUDIT_BYTES + 1)
        need(hashlib.sha256(raw).hexdigest() == ref['sha256'], 'SOURCE_CHANGED_DURING_ANALYSIS')


def inspect_original(audit_directory, bundle_paths):
    refs = []
    fallback = {'kind': 'FlowParameterizationDraft', 'schema_version': '1.0', 'status': 'UNCONFIRMED',
                'execution_authority': False, 'ready_for_execution': False, 'candidate_flow': None,
                'revised_flow': None, 'parameter_source_table': [], 'fixed_variable_unknown_steps': [],
                'revision_diff': [], 'model_calls': 0, 'device_actions': 0}
    try:
        need(type(bundle_paths) in (tuple, list) and 1 <= len(bundle_paths) <= 16, 'AUDIT_INPUT_INVALID')
        directory = Path(audit_directory)
        request = load(directory / 'input.json', refs)
        result = load(directory / 'result.json', refs)
        bundles = [load(path, refs) for path in bundle_paths]
        raw = original_raw(result, directory, request, refs)
        out = propose_parameterization(request, raw, bundles, input_channel=result['evidence_channel'])
        out.update(original_model_status=result.get('status'), original_model_calls=result['calls'],
                   original_evidence_channel=result['evidence_channel'],
                   original_audit=str(directory.resolve()), source_refs=refs,
                   provenance_assurance='AUDIT_HASH_CHAIN_NOT_REMOTE_ATTESTATION')
        unchanged(refs)
        out['source_unchanged'] = True
        return out
    except AuditError as exc:
        fallback['status'] = str(exc)
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        fallback['status'] = 'AUDIT_INPUT_INVALID'
    fallback['source_refs'] = refs
    return fallback


def save_report(output_root, report):
    directory = Path(output_root) / str(uuid.uuid4())
    directory.mkdir(parents=True, exist_ok=False)
    # Fixed literal filenames, all new paths; original audits are never written.
    artifacts = {'parameter-source-table.json': report['parameter_source_table'],
                 'step-classification.json': report['fixed_variable_unknown_steps'],
                 'revision-diff.json': report['revision_diff'], 'source-refs.json': report.get('source_refs', []),
                 'report.json': report}
    hashes = []
    for name, value in artifacts.items():
        content = canonical(value)
        with (directory / name).open('x', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
        hashes.append({'file': name, 'sha256': hashlib.sha256(content.encode()).hexdigest()})
    with (directory / 'complete.json').open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(canonical({'artifacts': hashes, 'report_digest': digest(report), 'execution_authority': False}))
    return directory
