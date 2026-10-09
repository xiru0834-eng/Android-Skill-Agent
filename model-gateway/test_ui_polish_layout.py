import unittest
import xml.etree.ElementTree as ET
from ui_polish_check import validate_layout

def tree(button):
    return ET.fromstring('<hierarchy><node class="android.widget.ScrollView" bounds="[0,0][320,600]">'
        '<node class="android.widget.Button" resource-id="good" bounds="[20,50][300,98]"/>'+button+'</node></hierarchy>')

class LayoutCheckTests(unittest.TestCase):
    def test_viewport_clipped_button_not_a_small_target(self):
        rows=validate_layout(tree('<node class="android.widget.Button" resource-id="clipped" bounds="[20,590][300,600]"/>'),1)
        self.assertEqual([r['id'] for r in rows],['good'])
    def test_genuinely_small_inside_viewport_fails(self):
        with self.assertRaises(AssertionError):validate_layout(tree('<node class="android.widget.Button" resource-id="small" bounds="[20,120][300,130]"/>'),1)
    def test_radio_target_also_measured(self):
        rows=validate_layout(tree('<node class="android.widget.RadioButton" resource-id="choice" bounds="[20,120][68,168]"/>'),1)
        self.assertEqual([r['id'] for r in rows],['good','choice'])
    def test_narrow_radio_target_fails(self):
        with self.assertRaises(AssertionError):validate_layout(tree('<node class="android.widget.RadioButton" resource-id="narrow" bounds="[20,120][60,168]"/>'),1)
    def test_horizontal_clip_fails(self):
        with self.assertRaises(AssertionError):validate_layout(tree('<node class="android.widget.Button" resource-id="clip" bounds="[20,120][330,168]"/>'),1)

if __name__=='__main__':unittest.main()
