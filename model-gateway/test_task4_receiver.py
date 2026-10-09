"""Historical-file diagnostics are separate from the 237-slot primary matrix."""
import unittest
from unittest.mock import patch
from pathlib import Path
from task4_receiver import install,archived,restore_receiver
from task4_protocol import display_state


class ReceiverTests(unittest.TestCase):
    def test_install_never_touches_source_or_physical_device(self):
        for name in ['Task3Workflows','PortableSkill','other']:
            calls=[]
            def fake(serial,*args):
                calls.append(args)
                return name+'\nOK' if args[0]=='emu' else '1'
            with self.subTest(name=name),patch('task4_receiver.adb',side_effect=fake),self.assertRaisesRegex(RuntimeError,'WRONG_RECEIVER'):
                install(None)
            self.assertFalse(any(c[0]=='install' for c in calls))
    def test_install_refuses_existing_packages(self):
        calls=[]
        def fake(serial,*args):
            calls.append(args)
            if args[0]=='emu':return 'Task4Transfer\nOK'
            return '1' if 'getprop' in args else 'package:edu.sydney.probe'
        with patch('task4_receiver.adb',side_effect=fake),self.assertRaisesRegex(RuntimeError,'RECEIVER_NOT_FRESH'):install(None)
        self.assertFalse(any(c[0]=='install' for c in calls))
    def test_archived_files_match_frozen_demonstrations_and_original_export(self):
        for flow in ['P','R','V']:
            item=archived(flow)
            self.assertEqual(item['package']['skill']['version'],3)
            self.assertEqual(item['sourceAvd'],'PortableSkill')
            self.assertEqual(item['package']['skill']['source'],'AUTOMATED')
    def test_recycled_emulator_serial_cannot_install_to_original_avd(self):
        names=iter(['Task4Transfer','PortableSkill']);sent=[]
        def fake(serial,*args,**kwargs):
            if args[0]=='emu':return next(names)+'\nOK'
            if 'getprop' in args:return '1'
            if args[0]=='install':sent.append(args)
            return ''
        with patch('task4_receiver.adb',side_effect=fake),self.assertRaisesRegex(RuntimeError,'WRONG_RECEIVER'):install(None)
        self.assertEqual(sent,[])
    def test_wrong_receiver_never_gets_restore_writes(self):
        with patch('task4_receiver.gate',side_effect=RuntimeError('WRONG_RECEIVER')),patch('task4_receiver.adb') as send:
            with self.assertRaisesRegex(RuntimeError,'WRONG_RECEIVER'):restore_receiver({},None)
            send.assert_not_called()
    def test_restore_mismatch_is_failure_not_successful_exit(self):
        original=dict(state=display_state('Physical size: 720x1280','Physical density: 240','null'))
        changed=dict(state=display_state('Physical size: 720x1280','Physical density: 320','null'))
        with patch('task4_receiver.gate'),patch('task4_receiver.adb'),patch('task4_receiver.read_display',return_value=changed),patch('task4_receiver.write'):
            with self.assertRaisesRegex(RuntimeError,'DISPLAY_NOT_RESTORED'):restore_receiver(original,Path('unused-test-output'))


if __name__=='__main__':unittest.main()
