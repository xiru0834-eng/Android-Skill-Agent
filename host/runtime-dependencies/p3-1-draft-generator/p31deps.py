"""Load audited local predecessors only; no import names or paths from model input."""
from deployment_artifacts import artifact_rows, artifact_digest
import hashlib
import importlib
import json
from pathlib import Path
import sys
BASE = Path(__file__).resolve().parent
ROOT = Path('D:/Codex-deliveries/smarthome-ui-polish/c1-c2-common-r1/runtime-dependencies')

def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def verify_dependencies():
    rows = json.loads((BASE / 'dependency-pins.json').read_text(encoding='utf-8'))['files']
    for row in rows:
        if artifact_digest(Path(row['path'])) != row['sha256']:
            raise ValueError('PINNED_DEPENDENCY_CHANGED')
    return len(rows)

def trusted_import(name, directory):
    path = directory / (name + '.py')
    existing = sys.modules.get(name)
    if existing and Path(existing.__file__).resolve() != path.resolve():
        raise ValueError('DEPENDENCY_NAMESPACE_CONFLICT')
    sys.path.insert(0, str(directory))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(directory))
verify_dependencies()
P13 = ROOT / 'p1-3-flow-compiler'
P24 = ROOT / 'p1p2-seed-acceptance/candidate/p2-4-learning-bundle'
p13 = trusted_import('dependencies', P13)
profile = trusted_import('environment', P13)
contracts = p13.contracts
bundle_contract = trusted_import('bundle_contract', P24)
BundleStore = trusted_import('bundle_store', P24).BundleStore
LearningQueries = trusted_import('learning_queries', P24).LearningQueries

def public_capabilities():
    data = profile.audited_room_profile().to_dict()
    names = sorted({t['skill'] for t in data['targets'].values() if t['implemented']})
    rows = [{'entity_id': t['entity_id'], 'name': t['skill'], 'domain': t['domain'], 'unit': t['unit']} for t in data['targets'].values() if t['implemented']]
    registry_path = ROOT / 'p1-2-flow-contracts/legacy_registry_snapshot.json'
    return {'registry_sha256': contracts.SNAPSHOT['registry_sha256'], 'registry_snapshot_file_sha256': artifact_digest(registry_path), 'definitions': [{'name': n, **contracts.CAPS[n]} for n in names], 'entity_capabilities': rows, 'environment': data['environment'], 'scope': 'PINNED_SOURCE_SUPPORTED_SUBSET_NOT_LIVE_APPROVAL', 'native_flow_read_adapter': data['native_flow_read_adapter']}
