"""Pure deployment projection tests; fake ADB bytes, no device/model call."""
import hashlib,json,unittest
from unittest.mock import patch
from c2_lifecycle_cli import deployed_package
from c2_validation import compiler
class DeploymentTests(unittest.TestCase):
    def fixture(self):
        raw=json.dumps({'catalog':[{'device':'bedroom_light','capabilities':[{'skill':'SetPower'},{'skill':'SetBrightness'}]}]}).encode()
        profile=compiler.audited_room_profile().to_dict();profile['source_package_sha256']=hashlib.sha256(raw).hexdigest()
        return raw,profile
    def test_deployed_package_passes_original_contract(self):
        raw,p=self.fixture()
        prefs=('<map><string name="hash">'+hashlib.sha256(raw).hexdigest()+'</string></map>').encode()
        with patch('c2_lifecycle_cli.adb',side_effect=[raw,prefs]),patch('c2_lifecycle_cli.compiler.audited_room_profile') as profile:
            profile.return_value.to_dict.return_value=p
            package=deployed_package('R5CW134LLBZ')
        compiler.old.validate_document(package)
    def test_unreviewed_source_rejected_without_authority_fallback(self):
        raw,p=self.fixture()
        with patch('c2_lifecycle_cli.adb',side_effect=[raw,b'<map/>']),patch('c2_lifecycle_cli.compiler.audited_room_profile') as profile:
            profile.return_value.to_dict.return_value=p
            with self.assertRaisesRegex(ValueError,'LOCAL_PACKAGE_REVIEW_REQUIRED'):deployed_package('R5CW134LLBZ')
if __name__=='__main__':unittest.main()
