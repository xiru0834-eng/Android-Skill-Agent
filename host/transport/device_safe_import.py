"""Bounded, no-extraction knowledge reader. It never executes or approves a Flow."""
from dataclasses import dataclass
import io
import json
from pathlib import Path
import re
import stat
import struct
import zipfile
import zlib

from device_transport_deps import export, contracts

canonical, sha = export.canonical, export.sha
MAX_TOTAL, MAX_FILE, MAX_FILES = export.MAX_TOTAL, export.MAX_FILE, export.MAX_FILES
CORE = {'flow.json', 'environment.json', 'dependencies.json', 'knowledge.json', 'scope.json', 'description.json'}


class ImportErrorCode(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(ok, code):
    if not ok:
        raise ImportErrorCode(code)


def domain_valid(skill, domain):
    """A finite domain within the existing global capability contract."""
    try:
        cap = contracts.CAPS[skill]
        if type(domain) is not dict:
            return False
        if set(domain) == {'values'}:
            vals = domain['values']
            if type(vals) is not list or not 1 <= len(vals) <= 256:
                return False
            for val in vals: contracts._value_domain(val, cap)
            return len({(type(v), v) for v in vals}) == len(vals)
        if set(domain) != {'min', 'max', 'step'} or cap['type'] != 'integer':
            return False
        lo, hi, step = domain['min'], domain['max'], domain['step']
        if any(type(v) is not int for v in (lo, hi, step)) or not lo <= hi or step < 1:
            return False
        contracts._value_domain(lo, cap); contracts._value_domain(hi, cap)
        return (hi - lo) % step == 0
    except (KeyError, TypeError, contracts.ContractError):
        return False


def content_contract(documents, manifest):
    for filename, kind, code in (('flow.json', 'FlowSkill', 'FLOW_CONTRACT_ERROR'),
                                 ('environment.json', 'AppKnowledgePackage', 'PACKAGE_CONTRACT_ERROR')):
        try:
            require(documents[filename].get('kind') == kind, code)
            contracts.validate_document(documents[filename])
        except contracts.ContractError:
            raise ImportErrorCode(code) from None
    flow, package, deps = (documents[n] for n in ('flow.json', 'environment.json', 'dependencies.json'))
    require({'id': flow['id'], 'version': flow['version']} in package['flow_refs'], 'FLOW_REFERENCE_ERROR')
    require(manifest['app'] == {'package': package['environment']['app_package'],
                               'version': package['environment']['app_version']}, 'APP_CONTRACT_ERROR')
    require(set(deps) == {'declared', 'controller_profiles', 'profile_scope', 'native_flow_read_adapter'}
            and deps['declared'] == flow['dependencies']
            and deps['profile_scope'] == 'SOURCE_AUDIT_NOT_CURRENT_DEVICE'
            and deps['native_flow_read_adapter'] is True, 'DEPENDENCY_CONTRACT_ERROR')
    profiles = deps['controller_profiles']
    require(type(profiles) is dict and 1 <= len(profiles) <= 64, 'DEPENDENCY_CONTRACT_ERROR')
    entities = {e['entity_id']: e for e in package['entities']}
    capabilities = set(flow['dependencies']['capabilities'])
    fields = {'entity_id', 'skill', 'domain', 'unit', 'controller', 'reader', 'verifier', 'submission', 'implemented'}
    for key, profile in profiles.items():
        require(type(profile) is dict and set(profile) == fields, 'DEPENDENCY_CONTRACT_ERROR')
        skill, entity = profile['skill'], profile['entity_id']
        require(type(skill) is str and skill in capabilities and type(entity) is str and entity in entities,
                'DEPENDENCY_CONTRACT_ERROR')
        cap = contracts.CAPS[skill]
        require(key == entity + '.' + cap['property'] and skill in entities[entity]['capabilities']
                and domain_valid(skill, profile['domain']) and profile['unit'] == cap['unit']
                and profile['implemented'] is True and profile['submission'] == 'DIRECT'
                and profile['verifier'] == 'REOBSERVE_EQUALS_AND_PRESERVE_UNMENTIONED'
                and profile['controller'] == ('ACTION_CLICK' if skill == 'SetPower' else 'ACTION_SET_PROGRESS')
                and profile['reader'] == ('CHECKED_ON_OFF' if skill == 'SetPower' else 'RANGE_INFO_INTEGER'),
                'DEPENDENCY_CONTRACT_ERROR')
    require({p['skill'] for p in profiles.values()} == capabilities, 'DEPENDENCY_CONTRACT_ERROR')


def archive_layout(raw, entries, directory_start):
    """Reject extra payload outside JSON members and ambiguous local/central metadata."""
    offset = 0
    for i in entries:
        require(i.header_offset == offset and offset + 30 <= len(raw), 'UNSUPPORTED_ARCHIVE_LAYOUT')
        sig, _, flags, compression, _, _, _, _, _, namesize, extra = struct.unpack_from('<4s5H3I2H', raw, offset)
        require(sig == b'PK\x03\x04' and not extra and flags == i.flag_bits and compression == i.compress_type
                and raw[offset + 30:offset + 30 + namesize] == i.orig_filename.encode('ascii'), 'UNSUPPORTED_ARCHIVE_LAYOUT')
        offset += 30 + namesize + i.compress_size
    require(offset == directory_start and len(raw) >= 22, 'UNSUPPORTED_ARCHIVE_LAYOUT')
    sig, disk, diskdir, numdisk, numtotal, size, start, comment = struct.unpack_from('<4s4H2IH', raw, len(raw) - 22)
    require(sig == b'PK\x05\x06' and disk == diskdir == comment == 0 and numdisk == numtotal == len(entries)
            and start == directory_start and size == sum(46 + len(i.orig_filename) for i in entries)
            and start + size == len(raw) - 22, 'UNSUPPORTED_ARCHIVE_LAYOUT')


@dataclass(frozen=True)
class ReadPackage:
    _json: bytes
    sha256: str
    raw: bytes

    def documents(self):
        return json.loads(self._json)['documents']

    def manifest(self):
        return json.loads(self._json)['manifest']

    def receipt(self):
        return {'status': 'INTEGRITY_AND_CONTRACT_CHECKED', 'sha256': self.sha256,
                'package_id': self.manifest()['package_id'], 'version': self.manifest()['version'],
                'channel': 'DEVICE_VALIDATED_KNOWLEDGE', 'execution_authority': False,
                'ready_for_device_execution': False, 'source_trust': 'NOT_EVALUATED'}


def read_archive(raw):
    """One immutable bytes snapshot for hash, structure, policy and storage; no extraction."""
    require(type(raw) is bytes and 0 < len(raw) <= MAX_TOTAL, 'ARCHIVE_LIMIT')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            entries = z.infolist()
            require(1 < len(entries) <= MAX_FILES and sum(i.file_size for i in entries) <= MAX_TOTAL, 'ARCHIVE_LIMIT')
            require(len({i.orig_filename.casefold() for i in entries}) == len(entries), 'DUPLICATE_MEMBER')
            require(not z.comment, 'UNSUPPORTED_ARCHIVE_METADATA')
            for i in entries:
                export.safe_name(i.orig_filename)
                require(i.orig_filename == i.filename, 'BUNDLE_PATH_ERROR')
                require(i.filename == 'manifest.json' or i.filename in CORE or i.filename.startswith('evidence/'),
                        'UNSUPPORTED_MEMBER')
                mode = i.external_attr >> 16
                require(stat.S_IFMT(mode) in (0, stat.S_IFREG) and not mode & 0o111 and not i.is_dir(), 'UNSAFE_MEMBER_TYPE')
                require(not i.extra and not i.comment and not i.flag_bits & ~0x800,
                        'UNSUPPORTED_ARCHIVE_METADATA')
                require(i.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED), 'UNSUPPORTED_COMPRESSION')
                require(0 <= i.file_size <= MAX_FILE, 'ARCHIVE_LIMIT')
                require(i.file_size <= max(i.compress_size, 1) * 100, 'COMPRESSION_RATIO_LIMIT')
            archive_layout(raw, entries, z.start_dir)
            blobs = {}
            for i in entries:
                with z.open(i) as f:
                    blob = f.read(MAX_FILE + 1)
                require(len(blob) == i.file_size and len(blob) <= MAX_FILE, 'ARCHIVE_LIMIT')
                blobs[i.filename] = blob
    except export.ExportError as e:
        raise ImportErrorCode(e.code) from None
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, EOFError, OSError, zlib.error, struct.error):
        raise ImportErrorCode('ARCHIVE_READ_ERROR') from None
    require('manifest.json' in blobs and CORE <= set(blobs), 'REQUIRED_MEMBER_MISSING')
    try:
        manifest = export.decode(blobs.pop('manifest.json'))
        fields = {'format', 'schema_version', 'package_id', 'version', 'app', 'channel', 'formal_retrievable',
                  'execution_authority', 'verified_environments', 'files', 'manifest_sha256'}
        require(type(manifest) is dict and set(manifest) == fields, 'MANIFEST_SCHEMA_ERROR')
        core = {k: v for k, v in manifest.items() if k != 'manifest_sha256'}
        require(sha(canonical(core)) == manifest['manifest_sha256'], 'MANIFEST_INTEGRITY_ERROR')
        export.validate_data(manifest)
        require(manifest['format'] == export.FORMAT and manifest['schema_version'] == '2.0'
                and manifest['channel'] == 'DEVICE_VALIDATED_KNOWLEDGE' and manifest['formal_retrievable'] is False
                and manifest['execution_authority'] is False
                and type(manifest['verified_environments']) is list and len(manifest['verified_environments'])==1, 'MANIFEST_SCHEMA_ERROR')
        require(type(manifest['package_id']) is str and re.fullmatch(r'[a-z][a-z0-9_.-]{0,100}', manifest['package_id']), 'MANIFEST_SCHEMA_ERROR')
        require(type(manifest['version']) is str and re.fullmatch(r'(?:0|[1-9]\d{0,8})\.(?:0|[1-9]\d{0,8})\.(?:0|[1-9]\d{0,8})', manifest['version']), 'MANIFEST_SCHEMA_ERROR')
        rows = manifest['files']
        require(type(rows) is list and all(type(r) is dict and set(r) == {'path', 'bytes', 'sha256'} for r in rows), 'MANIFEST_SCHEMA_ERROR')
        require(all(type(r['path']) is str for r in rows) and len({r['path'] for r in rows}) == len(rows)
                and {r['path'] for r in rows} == set(blobs), 'MANIFEST_FILE_SET_ERROR')
        for row in rows:
            blob = blobs[row['path']]
            require(type(row['bytes']) is int and row['bytes'] == len(blob) and row['sha256'] == sha(blob), 'FILE_INTEGRITY_ERROR')
        documents = {name: export.decode(blob) for name, blob in blobs.items()}
        export.check_documents(documents)
        require(manifest['verified_environments']==documents['scope.json']['verified_environments'],'ENVIRONMENT_CONTRACT_ERROR')
        content_contract(documents, manifest)
    except export.ExportError as e:
        raise ImportErrorCode(e.code) from None
    except (UnicodeError, ValueError, TypeError, KeyError, RecursionError) as e:
        if isinstance(e, ImportErrorCode): raise
        raise ImportErrorCode('CONTENT_CONTRACT_ERROR') from None
    return ReadPackage(canonical({'manifest': manifest, 'documents': documents}), sha(raw), raw)


def read_path(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'ARCHIVE_PATH_ERROR')
    # A user-selected read-only input, never an extraction destination.
    with path.open('rb') as f:
        raw = f.read(MAX_TOTAL + 1)
    return read_archive(raw)


@dataclass(frozen=True)
class SourcePolicy:
    """Local operator fixture policy, not authenticated source identity or execution rights."""
    _entries: tuple

    def __init__(self, entries):
        require(type(entries) is dict and len(entries) <= 256, 'SOURCE_POLICY_ERROR')
        require(all(type(k) is str and re.fullmatch('[0-9a-f]{64}', k) and type(v) is str
                    and re.fullmatch('[a-z][a-z0-9-]{0,60}', v) for k, v in entries.items()), 'SOURCE_POLICY_ERROR')
        object.__setattr__(self, '_entries', tuple(sorted(entries.items())))

    def classify(self, package):
        require(type(package) is ReadPackage, 'UNVALIDATED_PACKAGE')
        return 'TRUSTED_LOCAL_SOURCE' if package.sha256 in dict(self._entries) else 'UNKNOWN_SOURCE'
