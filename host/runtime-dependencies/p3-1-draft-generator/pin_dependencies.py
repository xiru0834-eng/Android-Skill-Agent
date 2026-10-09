"""One-time baseline, not a runtime re-pinning or repair command."""
import hashlib
import json
from pathlib import Path

ROOT = Path('D:/Codex-deliveries/smarthome-ui-polish')
PATHS = [ROOT / 'p1-3-flow-compiler' / n for n in ('dependencies.py', 'dependency-pins.json', 'environment.py')]
PATHS += [ROOT / 'p1-2-flow-contracts' / n for n in ('contracts.py', 'contract_spec.json', 'legacy_registry_snapshot.json')]
PATHS += [ROOT / 'p1p2-seed-acceptance/candidate/p2-4-learning-bundle' / n for n in (
    'p24deps.py', 'dependency-pins.json', 'bundle_contract.py', 'bundle_store.py', 'learning_queries.py')]

if __name__ == '__main__':
    out = Path(__file__).with_name('dependency-pins.json')
    rows = [{'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in PATHS]
    with out.open('x', encoding='utf-8') as f:
        json.dump({'files': rows, 'scope': 'EXISTING_PREDECESSORS_NOT_NEW_DEVICE_PASS'}, f, indent=2)
    print('PINNED', len(rows))
