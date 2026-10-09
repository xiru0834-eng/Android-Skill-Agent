"""Fixed P1.2 parser/checker reuse. No input-driven imports or reference reads."""
from deployment_artifacts import artifact_rows, artifact_digest
import hashlib
import importlib.util
import json
from pathlib import Path
BASE = Path(__file__).resolve().parent
PINS = artifact_rows(json.loads((BASE / 'dependency-pins.json').read_text(encoding='utf-8'))['files'])

def verify_dependencies():
    for item in PINS:
        if artifact_digest(Path(item['path'])) != item['sha256']:
            raise ValueError('PINNED_DEPENDENCY_CHANGED')
    return len(PINS)
verify_dependencies()
_spec = importlib.util.spec_from_file_location('p21_pinned_p12_contracts', PINS[0]['path'])
contracts = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(contracts)

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))

def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()
