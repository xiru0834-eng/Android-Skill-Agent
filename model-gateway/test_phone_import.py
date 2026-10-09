import unittest
from xml.etree.ElementTree import fromstring
from phone_import import wait_picker, open_picker


class PickerTests(unittest.TestCase):
    def test_activity_settles_before_single_import_input(self):
        events = []
        ready = fromstring('<hierarchy><node resource-id="com.google.android.documentsui:id/dir_list" /></hierarchy>')
        open_picker(lambda: events.append('tap'), lambda: ready, lambda seconds: events.append(seconds))
        self.assertEqual(events, [1.0, 'tap'])

    def test_waits_for_picker_instead_of_reclicking_import(self):
        old = fromstring('<hierarchy><node resource-id="edu.sydney.probe:id/twoImport" /></hierarchy>')
        ready = fromstring('<hierarchy><node resource-id="com.google.android.documentsui:id/dir_list" /></hierarchy>')
        values = iter([old, old, ready]); waits = []
        self.assertIs(wait_picker(lambda: next(values), waits.append), ready)
        self.assertEqual(len(waits), 2)

    def test_absent_picker_stops_after_bound(self):
        empty = fromstring('<hierarchy/>'); calls = []
        def read(): calls.append(1); return empty
        with self.assertRaises(RuntimeError): wait_picker(read, lambda _: None)
        self.assertEqual(len(calls), 8)
