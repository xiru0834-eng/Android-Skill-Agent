import unittest
from repair_r3_restore import changes,NEW_OWNED


class RestoreScopeTest(unittest.TestCase):
    def test_known_current_run_files_only(self):
        old={'files/flow-user-result.json':b'old','files/user-recording.json':b'keep'}
        current=dict(old,**{'files/flow-user-result.json':b'experiment'})
        self.assertEqual(changes(old,current),['files/flow-user-result.json'])

    def test_unknown_user_change_blocks_before_overwrite(self):
        with self.assertRaisesRegex(ValueError,'UNOWNED_CHANGED_FILE'):
            changes({'files/user-recording.json':b'old'},{'files/user-recording.json':b'new'})

    def test_unrelated_files_are_not_deleted(self):
        self.assertIsNone(NEW_OWNED.fullmatch('files/my-skill.json'))
        self.assertIsNone(NEW_OWNED.fullmatch('shared_prefs/skills.xml'))
        self.assertIsNone(NEW_OWNED.fullmatch('../files/flow-user-result.json'))

    def test_current_approval_bytes_may_be_restored_not_imported(self):
        self.assertEqual(changes({'shared_prefs/flow_knowledge_review.xml':b'current'},
                                 {'shared_prefs/flow_knowledge_review.xml':b'experiment'}),
                         ['shared_prefs/flow_knowledge_review.xml'])


if __name__=='__main__':unittest.main()
