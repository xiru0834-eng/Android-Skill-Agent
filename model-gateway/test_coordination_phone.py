import unittest
from test_skill_selection import CATALOG
from phone_jev_ab import selection_call


class PhoneSelectionAdapterTests(unittest.TestCase):
    def test_local_choice_has_compatible_audit_and_no_remote_calls(self):
        for backend in ['routed','routed-full']:
            row=selection_call(backend,'执行阅读60',CATALOG)
            self.assertEqual(row['backend'],backend)
            self.assertEqual(row['selection']['skill_id'],'a'*64)
            self.assertTrue(row['available']);self.assertEqual(row['remoteCalls'],0)
            self.assertEqual(row['metadata']['model'],'literal-name')


if __name__=='__main__':unittest.main()
