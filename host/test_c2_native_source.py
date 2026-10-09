"""Source wiring assertions only; not actual UI/runtime qualification."""
import unittest
from pathlib import Path
N=Path(__file__).parent/'native/app/src/main'
class WiringTests(unittest.TestCase):
    def test_candidate_uses_same_service_not_lab_driver(self):
        s=(N/'java/edu/sydney/probe/UserCandidateActivity.java').read_text(encoding='utf-8')
        self.assertIn('service.runCandidateFlow(plan,writes',s)
        service=(N/'java/edu/sydney/probe/ProbeService.java').read_text(encoding='utf-8')
        self.assertIn('runFlow(plan,writes,"CANDIDATE_VALIDATION",completion)',service)
        self.assertIn('portableCancelled==token&&portableActive',service)
        for word in ('FlowAuditReceiver','PUBLISHED_USER_TASK','performAction','dispatchGesture','oracle'):
            self.assertNotIn(word,s)
    def test_receipt_source_is_native_and_not_client_success(self):
        s=(N/'java/edu/sydney/probe/UserCandidateActivity.java').read_text(encoding='utf-8')
        self.assertIn('NORMAL_USER_CANDIDATE_UI',s);self.assertIn('c2-validation-',s)
        self.assertIn('UserCandidateGate',s)
    def test_native_entry_not_exported(self):
        self.assertIn('.UserCandidateActivity" android:exported="false"',(N/'AndroidManifest.xml').read_text(encoding='utf-8'))
    def test_learning_entry_connected(self):
        s=(N/'java/edu/sydney/probe/UserLearningActivity.java').read_text(encoding='utf-8')
        self.assertIn('UserCandidateActivity.class',s)
        self.assertNotIn('validate.setEnabled(false)',s)
if __name__=='__main__':unittest.main(verbosity=2)
