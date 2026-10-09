import unittest
from named_journey_device import scroll_points
from unittest.mock import patch
import xml.etree.ElementTree as ET

class OperatorScrollTests(unittest.TestCase):
    def test_clipped_target_above_needs_up(self):
        x,y1,x2,y2=scroll_points([24,232,1056,-358],[0,232,1080,2205]);self.assertLess(y1,y2)
    def test_target_below_needs_down(self):
        x,y1,x2,y2=scroll_points([24,2500,1056,2205],[0,232,1080,2205]);self.assertGreater(y1,y2)
    def test_unknown_target_searches_down(self):
        x,y1,x2,y2=scroll_points(None,[0,232,1080,2205]);self.assertGreater(y1,y2)
    def test_short_strokes_do_not_fling_past_middle_skill(self):
        _,y1,_,y2=scroll_points([24,2880,1056,2205],[0,232,1080,2205]);self.assertLessEqual(abs(y1-y2),.3*(2205-232))
    def test_small_viewport_can_reach_after_fifteen_short_scrolls(self):
        from named_journey_device import node
        def ui(bounds):
            root=ET.Element('hierarchy');ET.SubElement(root,'node',{'class':'android.widget.ScrollView','bounds':'[0,221][720,1217]'})
            ET.SubElement(root,'node',{'resource-id':'edu.sydney.probe:id/libraryRun3','bounds':bounds,'enabled':'true'});return root
        with patch('named_journey_device.tree',side_effect=[ui('[24,1500][696,1217]')]*15+[ui('[24,1006][696,1132]')]),patch('named_journey_device.adb') as adb,patch('named_journey_device.time.sleep'):
            result=node('test','libraryRun3');self.assertEqual(result.get('bounds'),'[24,1006][696,1132]');self.assertEqual(adb.call_count,15)
