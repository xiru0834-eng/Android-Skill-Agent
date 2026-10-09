import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET
from workflow_capture import click

def ui(bounds, duplicate=False):
    child=f'<node resource-id="edu.sydney.probe:id/flowRun" enabled="true" bounds="{bounds}" />'
    return ET.fromstring('<hierarchy><node class="android.widget.ScrollView" bounds="[0,100][720,1200]">'+child+(child if duplicate else '')+'</node></hierarchy>')

class WorkbenchScrollTests(unittest.TestCase):
    @patch('workflow_capture.time.sleep')
    @patch('workflow_capture.adb')
    @patch('workflow_capture.tree')
    def test_scrolls_clipped_control_panel_not_target_app(self,tree,adb,sleep):
        tree.side_effect=[ui('[0,1500][720,1200]'),ui('[0,500][720,600]')]
        click('device','flowRun')
        self.assertEqual(adb.call_args_list[0].args[3],'swipe')
        self.assertEqual(adb.call_args_list[1].args[3],'tap')
    @patch('workflow_capture.adb')
    @patch('workflow_capture.tree')
    def test_ambiguous_never_inputs(self,tree,adb):
        tree.return_value=ui('[0,500][720,600]',True)
        with self.assertRaises(RuntimeError):click('device','flowRun')
        adb.assert_not_called()

if __name__=='__main__':unittest.main()
