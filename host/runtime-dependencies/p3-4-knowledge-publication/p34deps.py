"""Fixed predecessor, not code or paths supplied by a model."""
from deployment_artifacts import artifact_rows, artifact_digest
import hashlib
import json
from pathlib import Path
import sys
import importlib
ROOT = Path('D:/Codex-deliveries/smarthome-ui-polish/c1-c2-common-r1/runtime-dependencies')
P33 = ROOT / 'p3-3-layered-validation'
EXPECTED = '4016a5956692a7838128838d19e443a06650fb70f6dbc3e8e06d42efb921e34d'

def verify_predecessor():
    manifest = json.loads((P33 / 'evidence/frozen-confirmation-r2/freeze.json').read_text(encoding='utf-8'))
    rows_hash = hashlib.sha256(json.dumps(manifest['files'], ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    if manifest['source_hash'] != EXPECTED or rows_hash != EXPECTED:
        raise ValueError('PREDECESSOR_BATCH_CHANGED')
    for row in manifest['files']:
        if artifact_digest(Path(row['path'])) != row['sha256']:
            raise ValueError('PREDECESSOR_FROZEN_DRIFT')
    return manifest

def trusted(name, root):
    existing = sys.modules.get(name)
    if existing is not None and Path(getattr(existing, '__file__', '')).resolve() != (root / (name + '.py')).resolve():
        raise ValueError('PREDECESSOR_NAMESPACE_CONFLICT')
    sys.path.insert(0, str(root))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(root))
PREDECESSOR = verify_predecessor()
p33 = trusted('p33deps', P33)
flow_store, records, adapter = (p33.flow_store, p33.records, p33.adapter)
compiler, canonical, digest, contracts = (p33.compiler, p33.canonical, p33.digest, p33.contracts)
material_io = trusted('material_io', P33)
audit_io = p33.audit_io
