"""Pinned read-only predecessor reuse; never resolve imports from query input."""
from deployment_artifacts import artifact_rows, artifact_digest
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
BASE = Path(__file__).resolve().parent
P23 = Path('D:/Codex-deliveries/smarthome-ui-polish/c1-c2-common-r1/runtime-dependencies/p2-3-interaction-trace')
PINS = artifact_rows(json.loads((BASE / 'dependency-pins.json').read_text(encoding='utf-8'))['files'])

def verify_dependencies():
    for item in PINS:
        path = Path(item['path'])
        if not path.is_file() or artifact_digest(path) != item['sha256']:
            raise ValueError('PINNED_DEPENDENCY_CHANGED')
    return len(PINS)

def load_predecessor(name):
    allowed = {'p23deps', 'trace_contract', 'navigation_graph', 'safe_navigation', 'interaction_trace', 'trace_store', 'historical_trace'}
    if name not in allowed:
        raise ValueError('IMPORT_NOT_ALLOWED')
    path = P23 / (name + '.py')
    if name in sys.modules:
        if Path(sys.modules[name].__file__).resolve() != path.resolve():
            raise ValueError('DEPENDENCY_NAMESPACE_CONFLICT')
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
verify_dependencies()
load_predecessor('p23deps')
from p23deps import canonical, digest, derive_page, validate_observation
from observation_identity import search_elements
