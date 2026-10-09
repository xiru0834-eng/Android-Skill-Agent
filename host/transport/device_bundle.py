"""Bounded JSON-only test bundle transport. Readback never imports or grants rights."""
import hashlib
import json
import math
from pathlib import Path
import re
import zipfile

MAX_FILE = 1024 * 1024
MAX_TOTAL = 8 * MAX_FILE
MAX_FILES = 64
REQUIRED = {'flow.json', 'environment.json', 'knowledge.json', 'scope.json'}
FORMAT = 'app_knowledge_bundle_android_v2'
DENIED = set(('password account username token apikey secret credential authorizationref '
              'inputpermit accessibilitynode binder gestureclosure oracle hiddenlocators hiddenanswers '
              'initialstate finalstate hostdeviceid resumeauthority task approvedrawpackagehash '
              'localapprovalverified cancellationtokenref modeloriginal screenshot pixels script code').split())
DENIED_FAMILIES = ('password', 'token', 'secret', 'credential', 'apikey', 'oracle', 'hiddenanswer',
                  'inputpermit', 'authorizationref', 'resumeauthority', 'screenshot', 'imagebase64')
SECRET = re.compile(r'sk-(?:proj-|ws-)?[A-Za-z0-9._-]{20,}|Bearer\s+\S+|'
    r'(?i:password|api[_ -]?key|token|secret)\s*[=:]|-----BEGIN .*PRIVATE KEY|'
    r'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|'
    r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|'
    r'[A-Za-z]:[/\\]|\\\\[^\\]|/(?:home|Users|tmp|etc)/|https?://|file://')


class ExportError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def need(ok, code):
    if not ok:
        raise ExportError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def validate_data(value):
    count = 0

    def visit(item, depth=0):
        nonlocal count
        count += 1
        need(depth <= 32 and count <= 10000, 'DATA_LIMIT')
        if type(item) is dict:
            for key, child in item.items():
                need(type(key) is str, 'JSON_DATA_REQUIRED')
                normalized = re.sub(r'[^a-z0-9]', '', key.lower())
                need(normalized not in DENIED and not any(term in normalized for term in DENIED_FAMILIES),
                     'SENSITIVE_FIELD')
                if normalized in {'executionauthority', 'formalretrievable', 'modeluploadauthorized'}:
                    need(child is False, 'AUTHORITY_NOT_EXPORTABLE')
                if normalized == 'availabletools':
                    need(type(child) is list and not child, 'AUTHORITY_NOT_EXPORTABLE')
                need(not SECRET.search(key), 'SENSITIVE_VALUE')
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item: visit(child, depth + 1)
        else:
            need(item is None or type(item) in (str, bool, int, float), 'JSON_DATA_REQUIRED')
            if type(item) is float: need(math.isfinite(item), 'JSON_DATA_REQUIRED')
            if type(item) is str: need(len(item) <= 65536 and not SECRET.search(item), 'SENSITIVE_VALUE')
    visit(value)
    need(len(canonical(value)) <= MAX_FILE, 'DATA_LIMIT')


def safe_name(name):
    need(type(name) is str and len(name) <= 120 and
         re.fullmatch(r'(?:[a-z][a-z0-9_-]*/)*[a-z][a-z0-9_-]*\.json', name), 'BUNDLE_PATH_ERROR')


def check_documents(documents):
    need(type(documents) is dict and REQUIRED <= set(documents) and len(documents) < MAX_FILES,
         'CONTENT_CONTRACT_ERROR')
    evidence_ids = set()
    for name, obj in documents.items():
        safe_name(name)
        need(name != 'manifest.json', 'BUNDLE_PATH_ERROR')
        validate_data(obj)
        need(type(obj) is dict, 'CONTENT_CONTRACT_ERROR')
        if name.startswith('evidence/'):
            need(type(obj.get('id')) is str and obj['id'] not in evidence_ids, 'DUPLICATE_EVIDENCE_ID')
            evidence_ids.add(obj['id'])
    scope = documents['scope.json']
    need(scope.get('channel') == 'DEVICE_VALIDATED_KNOWLEDGE' and scope.get('formal_retrievable') is False
         and scope.get('execution_authority') is False and scope.get('verified_environments') == [documents['environment.json']['environment']],
         'FORMAL_EXPORT_BLOCKED')
    instance = scope.get('source_instance_scope')
    need(type(instance) is dict and set(instance) == {'account_scope', 'site_scope', 'cross_user_identity_guaranteed'}
         and instance['account_scope'] == 'EXPERIMENT_NO_ACCOUNT' and instance['site_scope'] == 'PARAMETER_ROOM_LOCAL_STATE'
         and instance['cross_user_identity_guaranteed'] is False, 'INSTANCE_SCOPE_ERROR')
    slots = scope.get('semantic_slots')
    need(type(slots) is list and slots and all(type(s) is dict and
         set(s) == {'name', 'requires_target_resolution'} and type(s['name']) is str
         and s['requires_target_resolution'] is True for s in slots), 'INSTANCE_SCOPE_ERROR')

    id_refs = []

    def references(item):
        if type(item) is dict:
            for key, child in item.items():
                if key == 'ref':
                    need(type(child) is str and child in documents and child.startswith('evidence/'),
                         'REFERENCE_NOT_BUNDLED')
                if key in {'evidence_refs', 'documentation_refs'}:
                    need(type(child) is list, 'EVIDENCE_ID_NOT_BUNDLED')
                    id_refs.extend(child)
                references(child)
        elif type(item) is list:
            for child in item: references(child)
    references(documents)
    need(all(type(r) is str and r in evidence_ids for r in id_refs), 'EVIDENCE_ID_NOT_BUNDLED')


def write_bundle(output, documents, *, package_id, version, app):
    """Exclusive-create test ZIP. No caller may upgrade channel or approval."""
    need(type(package_id) is str and re.fullmatch(r'[a-z][a-z0-9_.-]{0,100}', package_id), 'PACKAGE_ID_ERROR')
    need(type(version) is str and re.fullmatch(r'\d+\.\d+\.\d+', version), 'PACKAGE_VERSION_ERROR')
    need(type(app) is dict and set(app) == {'package', 'version'} and
         all(type(v) is str and v for v in app.values()), 'APP_SCHEMA_ERROR')
    validate_data(app)
    check_documents(documents)
    files = {name: canonical(obj) for name, obj in documents.items()}
    need(sum(map(len, files.values())) <= MAX_TOTAL - MAX_FILE, 'DATA_LIMIT')
    core = {'format': FORMAT, 'schema_version': '2.0', 'package_id': package_id, 'version': version,
        'app': app, 'channel': 'DEVICE_VALIDATED_KNOWLEDGE', 'formal_retrievable': False, 'execution_authority': False,
        'verified_environments': documents['scope.json']['verified_environments'], 'files': [{'path': n, 'bytes': len(raw), 'sha256': sha(raw)}
                                             for n, raw in sorted(files.items())]}
    files['manifest.json'] = canonical({**core, 'manifest_sha256': sha(canonical(core))})
    output = Path(output)
    need(not output.exists(), 'OUTPUT_EXISTS')
    # No partial artifact is considered complete; readback must validate every member.
    with output.open('xb') as stream, zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as z:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o600 << 16
            z.writestr(info, raw)
    return {'path': str(output), 'sha256': sha(output.read_bytes()), 'bytes': output.stat().st_size,
            'execution_authority': False}


def _object(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def decode(raw):
    try:
        return json.loads(raw.decode('utf-8'), object_pairs_hook=_object)
    except (UnicodeError, ValueError, RecursionError):
        raise ExportError('JSON_DECODE_ERROR') from None


def inspect_bundle(path):
    """Integrity readback only. No extraction, registration, current-state or rights."""
    path = Path(path)
    need(path.is_file() and not path.is_symlink() and path.stat().st_size <= MAX_TOTAL, 'BUNDLE_FILE_ERROR')
    try:
        with zipfile.ZipFile(path) as z:
            entries = z.infolist()
            need(1 < len(entries) <= MAX_FILES and len({i.filename for i in entries}) == len(entries), 'BUNDLE_MEMBER_ERROR')
            need(sum(i.file_size for i in entries) <= MAX_TOTAL, 'DATA_LIMIT')
            for i in entries:
                safe_name(i.filename)
                need(i.file_size <= MAX_FILE and not i.flag_bits & 1, 'BUNDLE_MEMBER_ERROR')
            raw = {i.filename: z.read(i) for i in entries}
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError):
        raise ExportError('BUNDLE_READ_ERROR') from None
    need('manifest.json' in raw, 'MANIFEST_MISSING')
    manifest = decode(raw.pop('manifest.json'))
    fields = {'format', 'schema_version', 'package_id', 'version', 'app', 'channel', 'formal_retrievable',
              'execution_authority', 'verified_environments', 'files', 'manifest_sha256'}
    need(type(manifest) is dict and set(manifest) == fields, 'MANIFEST_SCHEMA_ERROR')
    core = {k: v for k, v in manifest.items() if k != 'manifest_sha256'}
    need(sha(canonical(core)) == manifest['manifest_sha256'], 'MANIFEST_INTEGRITY_ERROR')
    validate_data(manifest)
    need(manifest['format'] == FORMAT and manifest['schema_version'] == '2.0' and
         manifest['channel'] == 'DEVICE_VALIDATED_KNOWLEDGE' and manifest['execution_authority'] is False
         and manifest['formal_retrievable'] is False and type(manifest['verified_environments']) is list
         and len(manifest['verified_environments'])==1, 'MANIFEST_SCHEMA_ERROR')
    rows = manifest['files']
    need(type(rows) is list and all(type(r) is dict and set(r) == {'path', 'bytes', 'sha256'} for r in rows),
         'MANIFEST_SCHEMA_ERROR')
    need(all(type(r['path']) is str for r in rows) and len({r['path'] for r in rows}) == len(rows)
         and {r['path'] for r in rows} == set(raw), 'MANIFEST_FILE_SET_ERROR')
    for row in rows:
        blob = raw[row['path']]
        need(type(row['bytes']) is int and len(blob) == row['bytes'] and sha(blob) == row['sha256'], 'FILE_INTEGRITY_ERROR')
    documents = {name: decode(blob) for name, blob in raw.items()}
    check_documents(documents)
    return {'manifest': manifest, 'documents': documents, 'sha256': sha(path.read_bytes()),
            'execution_authority': False}
