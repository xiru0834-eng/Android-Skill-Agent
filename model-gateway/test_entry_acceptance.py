"""The evidence wrapper must not turn local green tests into full acceptance."""
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import entry_acceptance

from entry_acceptance import local_network_only, readiness, write_bundle


class AcceptanceSealTests(unittest.TestCase):
    def test_green_local_checks_do_not_authorize_second_step(self):
        summary = readiness(True, True)
        self.assertEqual(summary["localVerdict"], "PASS")
        self.assertFalse(summary["secondStepReady"])
        self.assertEqual(summary["overall"], "NOT_READY")
        self.assertIn("real_gpt_confirmation", summary["missingEvidence"])

    def test_any_failed_local_check_blocks_local_and_full_verdict(self):
        for python_ok, java_ok in [(False, True), (True, False), (False, False)]:
            with self.subTest(python=python_ok, java=java_ok):
                summary = readiness(python_ok, java_ok)
                self.assertEqual(summary["localVerdict"], "FAIL")
                self.assertFalse(summary["secondStepReady"])

    def test_output_cannot_overwrite_previous_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "bundle"
            write_bundle(target, {"overall": "NOT_READY"}, [])
            with self.assertRaises(FileExistsError):
                write_bundle(target, {"overall": "PASS"}, [])

    def test_external_connections_are_blocked_without_spending(self):
        # Even the RED phase must never touch a real external destination.
        with patch.object(socket.socket, "connect_ex",
                          side_effect=AssertionError("unsafe kernel call reached")):
            with local_network_only():
                with socket.socket() as channel:
                    with self.assertRaisesRegex(PermissionError, "EXTERNAL_NETWORK_FORBIDDEN"):
                        channel.connect(("192.0.2.1", 443))
                    with self.assertRaisesRegex(PermissionError, "EXTERNAL_NETWORK_FORBIDDEN"):
                        channel.connect_ex(("192.0.2.1", 443))

    def test_capture_supports_utf8_reconfigure_used_by_existing_modules(self):
        capture = entry_acceptance.EvidenceCapture()
        capture.reconfigure(encoding="utf-8")
        capture.write("中文证据")
        self.assertEqual(capture.getvalue(), "中文证据")

    def test_source_changed_during_tests_cannot_receive_green_verdict(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "owned.py"
            source.write_bytes(b"before")
            frozen = entry_acceptance.freeze_sources([source], Path(temporary))
            source.write_bytes(b"after")
            current = entry_acceptance.freeze_sources([source], Path(temporary))
            summary = readiness(True, True)
            entry_acceptance.check_source_identity(summary, frozen, current)
            self.assertEqual(summary["localVerdict"], "FAIL")
            self.assertFalse(summary["sourceStable"])
            self.assertEqual(summary["changedSources"], ["owned.py"])
            self.assertEqual(frozen["bytes"]["owned.py"], b"before")

    def test_unchanged_source_snapshot_preserves_local_verdict(self):
        snapshot = {"manifest": {"owned.py": "a"}, "bytes": {"owned.py": b"a"}}
        summary = readiness(True, True)
        entry_acceptance.check_source_identity(summary, snapshot, snapshot)
        self.assertEqual(summary["localVerdict"], "PASS")
        self.assertTrue(summary["sourceStable"])

    def test_race_suite_expands_eight_schedules_into_traceable_repeats(self):
        suite=entry_acceptance.race_suite(50)
        self.assertEqual(suite.countTestCases(),400)
        self.assertEqual(len({case.evidence_trial_id for case in suite}),400)

    def test_race_repeat_count_has_a_strict_finite_cap(self):
        for count in [True,1.0,0,51]:
            with self.subTest(count=count),self.assertRaises(ValueError):
                entry_acceptance.race_suite(count)


if __name__ == "__main__":
    unittest.main()
