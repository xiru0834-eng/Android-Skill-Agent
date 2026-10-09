"""Operator plumbing only; these mocks are never counted as Android experiments."""
import unittest
import hashlib
import xml.etree.ElementTree as ET
from unittest.mock import patch
import task3_device_checks as device


class OperatorTests(unittest.TestCase):
    def test_control_clipped_above_viewport_scrolls_up_not_further_down(self):
        def view(bounds):
            return ET.fromstring('<hierarchy><node class="android.widget.ScrollView" bounds="[0,100][720,1200]"><node resource-id="edu.sydney.probe:id/libraryRun3" bounds="'+bounds+'" enabled="true" clickable="true"/></node></hierarchy>')
        for bounds in ['[30,100][690,-150]','[30,90][690,150]']:
            with self.subTest(bounds=bounds),patch.object(device,'tree',side_effect=[view(bounds),view('[30,300][690,372]')]),patch.object(device,'adb') as dispatch:
                device.management_control('libraryRun3',clock=lambda:0,sleep=lambda _:None)
                first,last=dispatch.call_args_list
                self.assertEqual(first.args[3],'swipe')
                self.assertLess(first.args[5],first.args[7])
                self.assertEqual(last.args[3],'tap')
                self.assertEqual(dispatch.call_count,2)

    def test_read_only_transition_retry_does_not_repeat_inputs(self):
        root=ET.fromstring('<hierarchy><node/></hierarchy>')
        ticks=iter([0,0,1,2])
        with patch.object(device,'raw_tree',side_effect=[RuntimeError('No allowed UI evidence'),root]),patch.object(device,'adb') as dispatch:
            self.assertIs(device.preparation_tree(device.SERIAL,clock=lambda:next(ticks),sleep=lambda _:None),root)
            dispatch.assert_not_called()
        ticks=iter([0,0,1,7])
        with patch.object(device,'raw_tree',side_effect=RuntimeError('No allowed UI evidence')),patch.object(device,'adb') as dispatch:
            with self.assertRaisesRegex(RuntimeError,'PREPARATION_OBSERVATION_TIMEOUT'):
                device.preparation_tree(device.SERIAL,clock=lambda:next(ticks),sleep=lambda _:None)
            dispatch.assert_not_called()
    def test_management_wait_is_bounded_and_never_clicks_during_transition(self):
        ready=ET.fromstring('<hierarchy><node><node class="android.widget.ScrollView" bounds="[0,100][720,1200]"><node resource-id="edu.sydney.probe:id/teachSave" bounds="[30,1000][690,1100]" enabled="true" clickable="true"/></node></node></hierarchy>')
        transition=ET.fromstring('<hierarchy><node/></hierarchy>')
        clock=iter([0,0,1,2,3])
        with patch.object(device,'tree',side_effect=[transition,ready]),patch.object(device,'adb') as input_call:
            device.management_control('teachSave',clock=lambda:next(clock),sleep=lambda _:None)
            self.assertEqual(input_call.call_count,1)
            self.assertEqual(input_call.call_args.args[1:4],('shell','input','tap'))
        clock=iter([0,0,7])
        with patch.object(device,'tree',return_value=transition),patch.object(device,'adb') as input_call:
            with self.assertRaisesRegex(RuntimeError,'MANAGEMENT_TRANSITION_TIMEOUT'):
                device.management_control('teachSave',clock=lambda:next(clock),sleep=lambda _:None)
            input_call.assert_not_called()
    def test_hidden_approval_controls_never_clicked(self):
        def ui(bottom=1160):
            return ET.fromstring('<hierarchy><node bounds="[54,60][666,1220]"><node resource-id="android:id/button1" bounds="[552,1100][648,'+str(bottom)+']" enabled="true" clickable="true"/><node resource-id="android:id/button2" bounds="[456,1100][552,1160]" enabled="true" clickable="true"/></node></hierarchy>')
        self.assertTrue(device.review_controls(ui()))
        for bottom in [1100,1099,1280]:
            with self.subTest(bottom=bottom),self.assertRaises(RuntimeError):device.review_controls(ui(bottom))
    def test_all_installed_binary_identities_checked_before_task(self):
        sha=hashlib.sha256(b'candidate').hexdigest()
        versions={device.PROBE:40,device.APP:6,'edu.sydney.evaluation':4}
        def response(serial,*args):
            if args[:3]==('emu','avd','name'):return 'Task3Workflows\nOK'
            if args[:3]==('shell','dumpsys','package'):return 'versionCode='+str(versions[args[3]])
            if args[:3]==('shell','pm','path'):return 'package:/'+args[3]+'.apk'
            if args[:2]==('shell','sha256sum'):return sha+'  '+args[2]
            raise AssertionError('Unexpected mutating or unknown command')
        with patch.object(device,'adb',side_effect=response),patch.object(device.Path,'read_bytes',return_value=b'candidate'):
            self.assertEqual(len(device.gate()['artifacts']),3)
            versions['edu.sydney.evaluation']=3
            with self.assertRaisesRegex(RuntimeError,'WRONG_AUXILIARY_VERSION'):device.gate()
            versions['edu.sydney.evaluation']=4;sha='0'*64
            with self.assertRaisesRegex(RuntimeError,'WRONG_APK'):device.gate()

    def test_fresh_preferences_are_empty_only_for_missing_file(self):
        with patch.object(device,'prefs',side_effect=RuntimeError('No such file or directory')):
            self.assertEqual(device.optional_prefs(),{})
        with patch.object(device,'prefs',side_effect=RuntimeError('Permission denied')):
            with self.assertRaises(RuntimeError):device.optional_prefs()


if __name__=='__main__':unittest.main()
