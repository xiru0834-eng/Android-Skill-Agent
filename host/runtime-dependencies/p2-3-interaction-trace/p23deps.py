"""Hash-pinned additive reuse, never input-driven imports or permissions."""
from deployment_artifacts import artifact_rows, artifact_digest
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
BASE = Path(__file__).resolve().parent
PINS = artifact_rows(json.loads((BASE / 'dependency-pins.json').read_text(encoding='utf-8'))['files'])
P22 = Path('D:/Codex-deliveries/smarthome-ui-polish/c1-c2-common-r1/runtime-dependencies/p2-2-page-observation')

def verify_dependencies():
    for item in PINS:
        path = Path(item['path'])
        if not path.is_file() or artifact_digest(path) != item['sha256']:
            raise ValueError('PINNED_DEPENDENCY_CHANGED')
    return len(PINS)
verify_dependencies()
for name in ('p22deps', 'observation_tree', 'observation_capture', 'observation_contract', 'observation_identity'):
    path = P22 / (name + '.py')
    if name in sys.modules:
        if Path(sys.modules[name].__file__).resolve() != path.resolve():
            raise ValueError('DEPENDENCY_NAMESPACE_CONFLICT')
        continue
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
from p22deps import LearningBudget, ScopeAuthorization, ScopeError, validate_scope, scope_digest, canonical, digest
from observation_contract import validate_observation
from observation_identity import derive_page
from observation_capture import ObservationCollector, VALID
from observation_tree import plain_copy, identifier, ObservationError
