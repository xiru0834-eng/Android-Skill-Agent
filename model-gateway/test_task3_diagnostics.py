"""Read-only ANR attribution parsing; no runtime success claim."""
import unittest
from task3_diagnostics import probe_main_stack


class DiagnosticTests(unittest.TestCase):
    def test_crlf_own_main_stack_is_retained_without_other_threads(self):
        raw='Cmd line: edu.sydney.probe\r\nBuild: lab\r\n"main" Runnable\r\n at android.text.DynamicLayout.reflow\r\n\r\n"binder" Native\r\n secret-other-thread\r\n'
        value=probe_main_stack(raw)
        self.assertIn('DynamicLayout.reflow',value)
        self.assertNotIn('secret-other-thread',value)
    def test_other_process_main_cannot_be_borrowed(self):
        raw='Cmd line: edu.sydney.probe\nno-main\nCmd line: other.app\n"main" Runnable\n wrong-stack\n'
        self.assertIsNone(probe_main_stack(raw))
    def test_non_probe_stack_is_not_collected(self):
        self.assertIsNone(probe_main_stack('Cmd line: other.app\n"main" Runnable\n wrong-stack\n'))


if __name__=='__main__':unittest.main()
