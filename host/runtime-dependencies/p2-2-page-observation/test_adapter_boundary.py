"""Source-only interface checks, not Android runtime or gate proof."""
from pathlib import Path
import unittest

BASE = Path(__file__).resolve().parent


class AdapterBoundaryTests(unittest.TestCase):
    def test_native_adapter_has_default_deny_and_no_input_or_screenshot_calls(self):
        source = (BASE / 'native/edu/sydney/probe/P22ReadOnlyTreeAdapter.java').read_text(encoding='utf-8')
        for token in ('performAction(', 'dispatchGesture(', 'performGlobalAction(', 'startActivity(', 'takeScreenshot('):
            self.assertNotIn(token, source)
        self.assertIn('private static final ObservationAuthority DENY', source)
        start = source.index('public JSONObject copyCurrentTree')
        self.assertLess(source.index('gate(app, deadlineElapsedMs)', start), source.index('service.getRootInActiveWindow()', start))
        self.assertIn('PortableWindowGuard.frame(root, windows)', source)
        self.assertIn('NATIVE_TREE_COPY_NOT_OBSERVATION_PIPELINE', source)

    def test_offline_implementation_has_no_device_network_or_model_tool_import(self):
        files = ('observation_tree.py','observation_capture.py','observation_contract.py','observation_identity.py','observation_store.py')
        for name in files:
            source = (BASE / name).read_text(encoding='utf-8')
            for token in ('import requests','import openai','import subprocess','import socket','adb ', 'run-as ', 'oracle'):
                with self.subTest(file=name, token=token): self.assertNotIn(token, source)

    def test_read_queries_do_not_invoke_capture(self):
        source = (BASE / 'observation_store.py').read_text(encoding='utf-8')
        for token in ('ObservationCollector','read_frame(', 'request_screenshot(', 'observe(', 'performAction('):
            self.assertNotIn(token, source)


if __name__ == '__main__': unittest.main()
