"""Explicit origin -> deployed artifact lineage, never execution authority.

Legacy frozen manifests retain their original bytes and hashes. A relocated
loader verifies BOTH the origin pin and actual deployed bytes via this sealed
manifest. Business/raw package hashes do not use this helper.
"""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
MANIFEST_SHA256 = 'ecac3c14d13feb759b959cbfd53c7b297fefb67eec8d45ec13ab5a1d18e9f691'
_INDEX_CACHE = None

def _key(path):
    return str(Path(path).resolve()).casefold()

def _index():
    global _INDEX_CACHE
    raw = (BASE/'deployment-manifest.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise ValueError('DEPLOYMENT_MANIFEST_CHANGED')
    # Cache only the immutable path index AFTER rechecking the manifest bytes.
    # Actual artifact bytes below are still checked on every guard invocation.
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE
    data = json.loads(raw)
    if data.get('kind') != 'PinnedArtifactDeployment' or data.get('execution_authority') is not False:
        raise ValueError('DEPLOYMENT_MANIFEST_INVALID')
    rows = {}
    for row in data['files']:
        target = Path(row['deployed_path']).resolve()
        if not target.is_relative_to((BASE/'runtime-dependencies').resolve()):
            raise ValueError('DEPLOYMENT_PATH_OUTSIDE_SCOPE')
        for path in (row['origin_path'], row['deployed_path']):
            key = _key(path)
            if key in rows and rows[key] != row:
                raise ValueError('DEPLOYMENT_ALIAS_CONFLICT')
            rows[key] = row
    _INDEX_CACHE = rows
    return rows

def artifact_digest(path):
    row = _index().get(_key(path))
    if row is None:
        raise ValueError('UNREGISTERED_PINNED_ARTIFACT')
    actual = hashlib.sha256(Path(row['deployed_path']).read_bytes()).hexdigest()
    if actual != row['deployed_sha256']:
        raise ValueError('DEPLOYED_ARTIFACT_CHANGED')
    return row['origin_sha256']

def artifact_rows(rows):
    index = _index()
    result = []
    for row in rows:
        entry = index.get(_key(row['path']))
        if entry is None or entry['origin_sha256'] != row['sha256']:
            raise ValueError('PINNED_ORIGIN_MISMATCH')
        artifact_digest(row['path'])
        result.append({**row, 'path': entry['deployed_path']})
    return result
