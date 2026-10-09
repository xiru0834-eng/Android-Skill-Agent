import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import entry_phone
import named_journey_device
from entry_phone import run


class EntryPhoneProtocolTests(unittest.TestCase):
    def test_emulator_library_waits_for_actual_input_window_before_followup_text(self):
        with patch('named_journey_device.home'),patch('named_journey_device.tap'),patch('named_journey_device.wait_input_ready') as ready:
            named_journey_device.library('emulator-5554')
            self.assertEqual(ready.call_args.args[1],'edu.sydney.probe/edu.sydney.probe.WorkflowLibraryActivity')
        with patch('named_journey_device.home'),patch('named_journey_device.tap'),patch('named_journey_device.wait_input_ready') as ready:
            named_journey_device.library('R5CW134LLBZ')
            ready.assert_not_called()
    def test_empty_text_uses_explicit_clear_extra_not_a_lost_shell_argument(self):
        with patch('named_journey_device.node'),patch('named_journey_device.adb',return_value='PASS UI text set') as operation:
            named_journey_device.text('serial','libraryInput','')
            self.assertIn('clearText',operation.call_args.args)
            self.assertNotIn('value',operation.call_args.args)
    def test_reverse_mapping_is_read_back_not_assumed_restored(self):
        with patch('entry_phone.adb',return_value='serial tcp:8765 tcp:9123\n'):
            self.assertEqual(entry_phone.reverse_target('serial'),'tcp:9123')
        with patch('entry_phone.adb',return_value='serial tcp:8766 tcp:9123\n'):
            self.assertIsNone(entry_phone.reverse_target('serial'))

    def test_empty_input_remains_empty_not_replaced_with_a_space(self):
        with patch('entry_phone.text') as set_text, \
             patch('entry_phone.library'),patch('entry_phone.home'), \
             patch('entry_phone.tree') as read_tree,patch('entry_phone.prefs',return_value={'text':None}):
            import xml.etree.ElementTree as ET
            read_tree.return_value=ET.fromstring('<hierarchy><node resource-id="edu.sydney.probe:id/libraryInput" text=""/></hierarchy>')
            self.assertTrue(entry_phone.restore_input('serial',''))
            set_text.assert_called_once_with('serial','libraryInput','')

    def test_input_restore_mismatch_is_reported(self):
        with patch('entry_phone.text'),patch('entry_phone.library'), \
             patch('entry_phone.home'),patch('entry_phone.tree') as read_tree:
            import xml.etree.ElementTree as ET
            read_tree.return_value=ET.fromstring('<hierarchy><node resource-id="edu.sydney.probe:id/libraryInput" text="wrong"/></hierarchy>')
            self.assertFalse(entry_phone.restore_input('serial','original'))

    def test_saturation_cannot_accidentally_start_paid_test_or_touch_phone(self):
        with tempfile.TemporaryDirectory() as folder, \
             patch('entry_phone.prefs',side_effect=AssertionError('phone must not be touched')), \
             patch('entry_phone.gpt_remote',side_effect=AssertionError('no paid call')):
            target=Path(folder)/'not-created'
            with self.assertRaisesRegex(ValueError,'SATURATION_REQUIRES_INJECTED_MODE'):
                run(target,injected=False,saturated_cancellations=True)
            self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
