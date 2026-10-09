"""Fixed, frozen predecessors. Never imports code chosen by a candidate."""
from deployment_artifacts import artifact_rows, artifact_digest
import hashlib
import importlib
import json
from pathlib import Path
import sys
ROOT = Path('D:/Codex-deliveries/smarthome-ui-polish/c1-c2-common-r1/runtime-dependencies')
P32, P14 = (ROOT / 'p3-2-flow-abstraction', ROOT / 'p1-4-flow-store-adapter')

def verify_predecessor():
    manifest = json.loads((P32 / 'evidence/frozen-confirmation-r1/freeze.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        if artifact_digest(Path(row['path'])) != row['sha256']:
            raise ValueError('PREDECESSOR_FROZEN_DRIFT')
    return manifest['source_hash']

def trusted(name, root):
    existing = sys.modules.get(name)
    if existing is not None and Path(getattr(existing, '__file__', '')).resolve() != (root / (name + '.py')).resolve():
        raise ValueError('PREDECESSOR_NAMESPACE_CONFLICT')
    sys.path.insert(0, str(root))
    try:
        return importlib.import_module(name)
    finally:
        sys.path.remove(str(root))
PREDECESSOR_HASH = verify_predecessor()
p32 = trusted('p32deps', P32)
abstraction = trusted('abstraction', P32)
revision = trusted('revision', P32)
audit_io = trusted('audit_io', P32)
p14 = trusted('p14deps', P14)
flow_store = trusted('flow_store', P14)
records = trusted('records', P14)
adapter = trusted('flow_adapter', P14)
compiler, environment, checks = (p14.compiler, p14.environment, p14.checks)
canonical, digest, contracts = (p14.canonical, p14.digest, p14.contracts)
