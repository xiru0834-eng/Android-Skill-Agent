"""Only pinned local code/data are loaded. No user-directed imports or file refs."""
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
spec = importlib.util.spec_from_file_location('p1_2_contracts_pinned', PINS[0]['path'])
contracts = importlib.util.module_from_spec(spec)
spec.loader.exec_module(contracts)

def digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))
