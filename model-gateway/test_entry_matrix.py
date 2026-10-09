import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
import entry_matrix
from entry_matrix import cases, mutate_reply, summarize, verify_input


class EntryMatrixTests(unittest.TestCase):
    def test_confirmation_wait_observes_delayed_dialog_without_extra_input(self):
        elapsed=[0.0]
        reads=[]
        def read(timeout):
            self.assertGreater(timeout,0)
            self.assertLessEqual(timeout,3)
            reads.append(elapsed[0])
            return ET.fromstring('<hierarchy><node resource-id="android:id/button1"/></hierarchy>' if elapsed[0]>=.6 else '<hierarchy/>')
        def sleep(delay):elapsed[0]+=delay
        ui=entry_matrix.wait_confirmation(read,clock=lambda:elapsed[0],sleep=sleep)
        self.assertTrue(entry_matrix.has_confirmation(ui))
        self.assertGreaterEqual(elapsed[0],.6)
        self.assertLessEqual(elapsed[0],3)

    def test_confirmation_wait_is_bounded_and_does_not_invent_a_dialog(self):
        elapsed=[0.0]
        def sleep(delay):elapsed[0]+=delay
        ui=entry_matrix.wait_confirmation(lambda timeout:ET.fromstring('<hierarchy/>'),clock=lambda:elapsed[0],sleep=sleep)
        self.assertFalse(entry_matrix.has_confirmation(ui))
        self.assertLessEqual(elapsed[0],3)
        self.assertGreaterEqual(elapsed[0],2.9)

    def test_confirmation_already_present_needs_no_sleep(self):
        ui=ET.fromstring('<hierarchy><node resource-id="android:id/button1"/></hierarchy>')
        with patch('entry_matrix.time.sleep',side_effect=AssertionError('no waiting needed')):
            self.assertIs(entry_matrix.wait_confirmation(lambda timeout:ui),ui)

    def test_slow_read_may_not_make_a_late_confirmation_pass(self):
        elapsed=[0.0]
        def read(timeout):
            elapsed[0]+=timeout+.01
            return ET.fromstring('<hierarchy><node resource-id="android:id/button1"/></hierarchy>')
        with self.assertRaisesRegex(RuntimeError,'CONFIRMATION_OBSERVATION_TIMEOUT'):
            entry_matrix.wait_confirmation(read,clock=lambda:elapsed[0],sleep=lambda delay:None)

    def test_empty_text_is_checked_against_persisted_text_not_accessibility_hint(self):
        with patch('entry_matrix.home'),patch('entry_matrix.library'),patch('entry_matrix.tree',return_value='REFRESHED'),patch('entry_matrix.prefs',return_value={'text':''}):
            self.assertEqual(verify_input('serial','','HINT_TREE'),'REFRESHED')
        with patch('entry_matrix.home'),patch('entry_matrix.library'),patch('entry_matrix.tree',return_value='REFRESHED'),patch('entry_matrix.prefs',return_value={'text':None}):
            self.assertEqual(verify_input('serial','','HINT_TREE'),'REFRESHED')
        with patch('entry_matrix.home'),patch('entry_matrix.library'),patch('entry_matrix.tree'),patch('entry_matrix.prefs',return_value={'text':'not empty'}):
            with self.assertRaisesRegex(AssertionError,'INPUT_NOT_PRESERVED'):verify_input('serial','','HINT_TREE')
    def test_phone_and_display_denominators_keep_unrun_cases(self):
        phone=cases(3);display=cases(2,display=True)
        self.assertEqual(len(phone),72);self.assertEqual(len(display),24)
        self.assertEqual(len({(c['caseId'],c['repeat']) for c in phone}),72)
        self.assertEqual(sum(c['automatable'] for c in phone),63)

    def test_invalid_response_mutations_are_distinct(self):
        body=dict(request_id='a'*32,status='invoke',skill_id='b'*64,message='Preview')
        for key in ['U18','U19','U20','U21','U22']:
            code,raw=mutate_reply(key,200,body)
            self.assertEqual(code,200);self.assertIsInstance(raw,bytes)
            self.assertNotEqual(raw,b'')
        self.assertGreater(len(mutate_reply('U20',200,body)[1]),4096)
        self.assertIn(b'"status":"reject","status":"invoke"',mutate_reply('U22',200,body)[1])

    def test_summary_cannot_turn_not_run_or_fault_stop_into_success(self):
        planned=cases(3)
        rows=[dict(caseId='U01',status='PASS'),dict(caseId='U02',status='FAIL'),dict(caseId='U10',status='NOT_RUN')]
        value=summarize(rows,planned)
        self.assertEqual(value['planned'],72)
        self.assertEqual(value['passed'],1)
        self.assertEqual(value['failed'],1)
        self.assertFalse(value['matrixPassed'])
        self.assertEqual(value['notRun'],70)


if __name__=='__main__':unittest.main()
