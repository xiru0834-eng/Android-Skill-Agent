"""Fixed P2.1 reuse; no input-driven paths/imports and no existing file edits."""
from deployment_artifacts import artifact_rows, artifact_digest
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
BASE = Path(__file__).resolve().parent
PINS = artifact_rows(json.loads((BASE / 'dependency-pins.json').read_text(encoding='utf-8'))['files'])

def verify_dependencies():
    for item in PINS:
        if artifact_digest(Path(item['path'])) != item['sha256']:
            raise ValueError('PINNED_DEPENDENCY_CHANGED')
    return len(PINS)
verify_dependencies()
for name, item in zip(('p21deps', 'learning_scope', 'learning_budget'), PINS):
    if name in sys.modules:
        if Path(sys.modules[name].__file__).resolve() != Path(item['path']).resolve():
            raise ValueError('DEPENDENCY_NAMESPACE_CONFLICT')
    else:
        spec = importlib.util.spec_from_file_location(name, item['path'])
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
from learning_scope import validate_scope, scope_digest, ScopeError, ScopeAuthorization
from learning_budget import LearningBudget
from p21deps import canonical, digest
