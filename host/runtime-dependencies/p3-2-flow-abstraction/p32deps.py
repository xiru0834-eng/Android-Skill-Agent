"""Frozen P3.1 reuse, with its original downstream dependency checks; no mutable repinning."""
from deployment_artifacts import artifact_rows, artifact_digest
import hashlib
import importlib
import json
from pathlib import Path
import sys
P31 = Path('D:/Codex-deliveries/smarthome-ui-polish/c1-c2-common-r1/runtime-dependencies/p3-1-draft-generator')

def verify_predecessor():
    manifest = json.loads((P31 / 'evidence/frozen-confirmation-r1/freeze.json').read_text(encoding='utf-8'))
    for row in manifest['product_files'] + manifest['materials']:
        if artifact_digest(Path(row['path'])) != row['sha256']:
            raise ValueError('PREDECESSOR_FROZEN_DRIFT')
    return manifest['source_hash']
PREDECESSOR_HASH = verify_predecessor()
sys.path.insert(0, str(P31))
try:
    for module_name in ('p31deps', 'learning_request', 'draft_generator'):
        existing = sys.modules.get(module_name)
        if existing is not None and Path(getattr(existing, '__file__', '')).resolve() != (P31 / (module_name + '.py')).resolve():
            raise ValueError('PREDECESSOR_NAMESPACE_CONFLICT')
    dependencies = importlib.import_module('p31deps')
    p31_request = importlib.import_module('learning_request')
    p31_draft = importlib.import_module('draft_generator')
finally:
    sys.path.remove(str(P31))
contracts = dependencies.contracts
bundle_contract = dependencies.bundle_contract
canonical, digest = (dependencies.canonical, dependencies.digest)
public_capabilities = dependencies.public_capabilities
