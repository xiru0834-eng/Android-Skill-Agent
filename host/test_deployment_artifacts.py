"""Pure deployment-contract fixtures; no model/device/approval use."""
import hashlib, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
import deployment_artifacts as artifacts

class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='c1-c2-deployment-')
        self.base=Path(self.tmp.name);self.folder=self.base/'runtime-dependencies';self.folder.mkdir()
        self.target=self.folder/'origin.py';self.target.write_bytes(b'deployed loader')
        self.origin=self.base/'absent-original.py'
        self.row={'origin_path':str(self.origin),'origin_sha256':hashlib.sha256(b'original loader').hexdigest(),
            'deployed_path':str(self.target),'deployed_sha256':hashlib.sha256(self.target.read_bytes()).hexdigest()}
        self.data={'kind':'PinnedArtifactDeployment','execution_authority':False,'files':[self.row]}
        self.stack=[];self.install()
    def install(self):
        raw=json.dumps(self.data).encode();(self.base/'deployment-manifest.json').write_bytes(raw)
        for p in reversed(self.stack):p.stop()
        self.stack=[patch.object(artifacts,'BASE',self.base),patch.object(artifacts,'MANIFEST_SHA256',hashlib.sha256(raw).hexdigest()),
            patch.object(artifacts,'_INDEX_CACHE',None)]
        for p in self.stack:p.start()
    def tearDown(self):
        for p in reversed(self.stack):p.stop()
        self.tmp.cleanup()
    def test_dual_hash_different_but_proven(self):
        self.assertNotEqual(self.row['origin_sha256'],self.row['deployed_sha256'])
        self.assertEqual(artifacts.artifact_digest(self.origin),self.row['origin_sha256'])
        self.assertEqual(artifacts.artifact_digest(self.target),self.row['origin_sha256'])
        self.assertFalse(self.origin.exists())
    def test_rows_keep_original_pin_and_relocate(self):
        old={'path':str(self.origin),'sha256':self.row['origin_sha256']}
        new=artifacts.artifact_rows([old])[0]
        self.assertEqual(new,{'path':str(self.target),'sha256':old['sha256']})
        self.assertEqual(old['path'],str(self.origin))
    def test_wrong_origin_pin_rejected(self):
        with self.assertRaisesRegex(ValueError,'PINNED_ORIGIN_MISMATCH'):
            artifacts.artifact_rows([{'path':str(self.origin),'sha256':'0'*64}])
    def test_unknown_path_rejected(self):
        with self.assertRaisesRegex(ValueError,'UNREGISTERED_PINNED_ARTIFACT'):artifacts.artifact_digest(self.base/'unknown')
    def test_file_change_even_after_cached_index(self):
        artifacts.artifact_digest(self.origin);self.target.write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'DEPLOYED_ARTIFACT_CHANGED'):artifacts.artifact_digest(self.origin)
    def test_manifest_change_even_after_cached_index(self):
        artifacts.artifact_digest(self.origin);(self.base/'deployment-manifest.json').write_bytes(b'{}')
        with self.assertRaisesRegex(ValueError,'DEPLOYMENT_MANIFEST_CHANGED'):artifacts.artifact_digest(self.origin)
    def test_missing_deployed_file(self):
        self.target.unlink()
        with self.assertRaises(FileNotFoundError):artifacts.artifact_digest(self.origin)
    def test_outside_scope_rejected(self):
        self.row['deployed_path']=str(self.base/'outside.py');self.install()
        with self.assertRaisesRegex(ValueError,'DEPLOYMENT_PATH_OUTSIDE_SCOPE'):artifacts.artifact_digest(self.origin)
    def test_alias_conflict_rejected(self):
        self.data['files'].append({**self.row,'origin_sha256':'0'*64});self.install()
        with self.assertRaisesRegex(ValueError,'DEPLOYMENT_ALIAS_CONFLICT'):artifacts.artifact_digest(self.origin)
    def test_authority_marker_rejected(self):
        self.data['execution_authority']=True;self.install()
        with self.assertRaisesRegex(ValueError,'DEPLOYMENT_MANIFEST_INVALID'):artifacts.artifact_digest(self.origin)

if __name__=='__main__':unittest.main()
