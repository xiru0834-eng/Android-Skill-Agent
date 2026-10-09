import unittest
from transfer_requests import dispatched_requests


def event(kind,step=0,identifier='a'):
    return dict(kind=kind,stepIndex=step,data=dict(id=identifier))


class RequestsTests(unittest.TestCase):
    def test_old_journal_unchanged(self):
        self.assertEqual(dispatched_requests([event('INPUT_REQUEST')],[dict(id='a')]),['a'])
    def test_aborted_request_is_not_input(self):
        self.assertEqual(dispatched_requests([event('INPUT_REQUEST'),event('INPUT_ABORTED')],[]),[])
    def test_mixed_requests(self):
        events=[event('INPUT_REQUEST'),event('INPUT_RETURN'),event('INPUT_REQUEST',1,'b'),event('INPUT_ABORTED',1,'b')]
        self.assertEqual(dispatched_requests(events,[dict(id='a')]),['a'])
    def test_orphan_abort_rejected(self):
        self.assertRaises(ValueError,dispatched_requests,[event('INPUT_ABORTED')],[])
    def test_wrong_abort_rejected(self):
        self.assertRaises(ValueError,dispatched_requests,[event('INPUT_REQUEST'),event('INPUT_ABORTED',0,'b')],[])
    def test_aborted_actual_action_rejected(self):
        self.assertRaises(ValueError,dispatched_requests,[event('INPUT_REQUEST'),event('INPUT_ABORTED')],[dict(id='a')])
    def test_duplicate_request_rejected(self):
        self.assertRaises(ValueError,dispatched_requests,[event('INPUT_REQUEST'),event('INPUT_REQUEST')],[dict(id='a')])
    def test_abort_after_return_rejected(self):
        self.assertRaises(ValueError,dispatched_requests,[event('INPUT_REQUEST'),event('INPUT_RETURN'),event('INPUT_ABORTED')],[])


if __name__=='__main__':unittest.main()
