"""Fixed versioned transport only; pinned original P1 schema remains unchanged."""
import hashlib,importlib.util
from pathlib import Path
import device_bundle as export
BASE=Path(__file__).resolve().parents[1]/'runtime-dependencies/p1-2-flow-contracts'
PINS={'contracts.py':'53f113e4bf1d0594272eac0cdcb2ead1ea63c204e46e660d02e00a9d74c854ce',
    'contract_spec.json':'ca15d1ef391b2b13cfc5c52f3976eff6fc95fcb0a1faab2d2bee964d67ba5ccb',
    'legacy_registry_snapshot.json':'8ec677a8d622806febcca5efa60f933bea3939ded3d2c48c23d87081294e34a0'}
for name,expected in PINS.items():
    if hashlib.sha256((BASE/name).read_bytes()).hexdigest()!=expected:raise ValueError('PINNED_CONTRACT_CHANGED')
spec=importlib.util.spec_from_file_location('device_transport_original_contracts',BASE/'contracts.py')
contracts=importlib.util.module_from_spec(spec);spec.loader.exec_module(contracts)
