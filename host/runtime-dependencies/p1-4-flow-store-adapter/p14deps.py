"""Load only the audited, pinned P1.3 modules, never imports named by a Flow."""
from deployment_artifacts import artifact_rows, artifact_digest
import hashlib
import importlib
import json
from pathlib import Path
import sys
BASE = Path(__file__).resolve().parent
P13 = Path('D:/Codex-deliveries/smarthome-ui-polish/c1-c2-common-r1/runtime-dependencies/p1-3-flow-compiler')

def verify_dependencies():
    pins = json.loads((BASE / 'dependency-pins.json').read_text(encoding='utf-8'))['files']
    for pin in pins:
        if artifact_digest(Path(pin['path'])) != pin['sha256']:
            raise ValueError('PINNED_DEPENDENCY_CHANGED')
    return len(pins)
verify_dependencies()
for name in ('compiler', 'cursor', 'checks', 'dependencies', 'environment', 'fixtures'):
    loaded = sys.modules.get(name)
    if loaded and Path(loaded.__file__).resolve().parent != P13.resolve():
        raise ValueError('MODULE_COLLISION')
sys.path.insert(0, str(P13))
compiler = importlib.import_module('compiler')
checks = importlib.import_module('checks')
cursor = importlib.import_module('cursor')
environment = importlib.import_module('environment')
dependencies = importlib.import_module('dependencies')
contracts = dependencies.contracts
canonical, digest = (dependencies.canonical, dependencies.digest)

def fixture_bundle(*args):
    """Explicit handwritten TEST_FIXTURE helper, not product App learning."""
    return importlib.import_module('fixtures').bundle(*args)
