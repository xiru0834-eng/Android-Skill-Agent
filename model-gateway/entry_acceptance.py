"""Offline first-step acceptance bundle. No providers, deployment or phone writes."""
import argparse
from contextlib import contextmanager, redirect_stderr, redirect_stdout
import hashlib
import io
import ipaddress
import json
from pathlib import Path
import socket
import subprocess
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
ENTRY_MODULES = [
    "test_entry_seal_boundaries", "test_entry_acceptance", "test_entry_bridge",
    "test_entry_roles", "test_entry_integration", "test_selection_deadline",
    "test_skill_selection", "test_selection_bridge", "test_contracts",
    "test_catalog_uniqueness", "test_named_identity", "test_deadline_remote",
    "test_compiler", "test_intent_bridge", "test_teaching_bridge",
    "test_entry_phone_protocol",
]
MISSING_EVIDENCE = [
    "device_confirmation_72", "display_matrix_96", "real_gpt_confirmation",
    "execution_handoff_75", "deployed_identity",
]
RACE_METHODS = [
    "test_entry_bridge.EntryBridgeTests.test_cancel_can_arrive_first_and_is_idempotent",
    "test_entry_bridge.EntryBridgeTests.test_cancel_does_not_wait_for_business_lock_and_no_late_delivery",
    "test_entry_seal_boundaries.HttpSealTests.test_accepted_id_has_cancellation_event_before_selector_entry",
    "test_entry_bridge.EntryBridgeTests.test_active_request_can_be_cancelled_when_unknown_tombstones_are_full",
    "test_entry_bridge.EntryBridgeTests.test_full_tombstone_set_does_not_grant_unauthenticated_known_cancellation",
    "test_entry_bridge.EntryBridgeTests.test_server_deadline_rejects_late_correct_result",
    "test_entry_bridge.EntryBridgeTests.test_deadline_does_not_retry_same_id_and_next_id_can_recover",
    "test_entry_bridge.EntryBridgeTests.test_busy_request_does_not_consume_budget_or_call_model",
]


def race_suite(repeats):
    if type(repeats) is not int or not 1<=repeats<=50:
        raise ValueError("RACE_REPEATS_MUST_BE_INTEGER_1_TO_50")
    suite=unittest.TestSuite()
    def leaves(branch):
        for child in branch:
            if isinstance(child,unittest.TestSuite):yield from leaves(child)
            else:yield child
    for repeat in range(repeats):
        for schedule,name in enumerate(RACE_METHODS):
            for case in leaves(unittest.TestLoader().loadTestsFromName(name)):
                case.evidence_trial_id=f"schedule-{schedule+1}-repeat-{repeat+1}"
                suite.addTest(case)
    return suite


@contextmanager
def fast_http_fixture(enabled):
    if not enabled:
        yield
        return
    from intent_bridge import BridgeServer
    original=BridgeServer.serve_forever
    def serve(self,poll_interval=.5):
        return original(self,poll_interval=.01)
    # Only test-server shutdown polling changes; product budgets are untouched.
    with patch.object(BridgeServer,"serve_forever",serve):yield


class EvidenceCapture(io.StringIO):
    def reconfigure(self, *, encoding="utf-8", **kwargs):
        # StringIO holds Unicode; logs are encoded once, when the bundle is saved.
        if encoding.lower().replace("_", "-") not in ("utf-8", "utf8"):
            raise ValueError("EVIDENCE_ENCODING_MUST_BE_UTF8")


@contextmanager
def local_network_only():
    """Tests can use literal loopback sockets; every other TCP destination fails."""
    original = socket.socket.connect
    original_ex = socket.socket.connect_ex
    def check_address(channel, address):
        if channel.family in (socket.AF_INET, socket.AF_INET6):
            try:
                allowed = ipaddress.ip_address(address[0]).is_loopback
            except (ValueError, TypeError, IndexError):
                allowed = False
            if not allowed:
                raise PermissionError("EXTERNAL_NETWORK_FORBIDDEN")
    def guarded(channel, address):
        check_address(channel, address)
        return original(channel, address)
    def guarded_ex(channel, address):
        check_address(channel, address)
        return original_ex(channel, address)
    with patch.object(socket.socket, "connect", guarded), patch.object(socket.socket, "connect_ex", guarded_ex):
        yield


def readiness(python_ok, java_ok):
    local = "FAIL" if python_ok is False or java_ok is False else (
        "PASS" if python_ok is True and java_ok is True else "PARTIAL")
    return dict(localVerdict=local, overall="NOT_READY", secondStepReady=False,
                missingEvidence=MISSING_EVIDENCE.copy(), paidCalls=0,
                scope="offline unit / localhost injected transport / Java core only")


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []
        self.starts = {}

    def startTest(self, test):
        self.starts[test.id()] = time.monotonic()
        super().startTest(test)

    def record(self, test, outcome, kind="method", error=None):
        self.rows.append(dict(testId=test.id(), kind=kind, outcome=outcome,
            trialId=getattr(test,"evidence_trial_id",None),
            elapsedMs=round((time.monotonic()-self.starts.get(test.id(), time.monotonic()))*1000, 3),
            errorType=error[0].__name__ if error else None))

    def addSuccess(self, test):
        self.record(test, "PASS")
        super().addSuccess(test)

    def addFailure(self, test, error):
        self.record(test, "FAIL", error=error)
        super().addFailure(test, error)

    def addError(self, test, error):
        self.record(test, "ERROR", error=error)
        super().addError(test, error)

    def addSkip(self, test, reason):
        self.record(test, "SKIP")
        super().addSkip(test, reason)

    def addSubTest(self, test, subtest, error):
        self.record(subtest, "PASS" if error is None else "FAIL", "subtest", error)
        super().addSubTest(test, subtest, error)


def source_paths():
    sources = list((ROOT / "model-gateway").glob("*.py"))
    sources += list((ROOT / "model-gateway").glob("*.ps1"))
    for folder in ["android-agent-probe/app/src/main", "android-agent-probe/tests"]:
        sources += [p for p in (ROOT / folder).rglob("*") if p.is_file()]
    return sources + [ROOT / "android-agent-probe/test-core.ps1"]


def freeze_sources(sources, root=ROOT):
    contents = {source.relative_to(root).as_posix(): source.read_bytes() for source in sources}
    return {"manifest": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
            "bytes": contents}


def check_source_identity(summary, frozen, current):
    names = frozen["manifest"].keys() | current["manifest"].keys()
    changed = sorted(name for name in names if frozen["manifest"].get(name) != current["manifest"].get(name))
    summary.update(sourceStable=not changed, changedSources=changed)
    if changed:
        summary["localVerdict"] = "FAIL"
        summary["evidenceInvalidated"] = "SOURCE_CHANGED_DURING_TEST"


def write_bundle(target, summary, rows, log="", java_log="", frozen=None, current=None):
    target = Path(target)
    target.mkdir(parents=True, exist_ok=False)
    (target / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    with (target / "attempts.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=True) + "\n")
    (target / "python.log").write_text(log, encoding="utf-8")
    (target / "java.log").write_text(java_log, encoding="utf-8")
    frozen = frozen if frozen is not None else freeze_sources(source_paths())
    current = current if current is not None else frozen
    (target / "source-manifest.json").write_text(json.dumps(frozen["manifest"], indent=2), encoding="utf-8")
    (target / "source-manifest-after.json").write_text(json.dumps(current["manifest"], indent=2), encoding="utf-8")
    # Save pre-test bytes, never a newer post-test edit; no preferences or keys.
    for name in ["intent_bridge.py", "selection_deadline.py", "skill_selection.py", "catalog_uniqueness.py",
                 "entry_acceptance.py", "test_entry_seal_boundaries.py", "test_entry_acceptance.py",
                 "entry_phone.py", "test_entry_phone_protocol.py"]:
        destination = target / "source" / name
        destination.parent.mkdir(exist_ok=True)
        destination.write_bytes(frozen["bytes"]["model-gateway/" + name])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--suite", choices=["boundaries", "entry", "all", "races"], default="entry")
    parser.add_argument("--race-repeats",type=int,default=50)
    parser.add_argument("--skip-java", action="store_true")
    args = parser.parse_args()
    target = args.output.resolve()
    if not target.is_relative_to(ROOT / "output/entry-stability-seal-v1"):
        parser.error("output must be a NEW child of output/entry-stability-seal-v1")
    if target.exists():
        parser.error("existing evidence must not be overwritten")
    frozen = freeze_sources(source_paths())
    capture = EvidenceCapture()
    with local_network_only(), fast_http_fixture(args.suite=="races"), redirect_stdout(capture), redirect_stderr(capture):
        loader = unittest.TestLoader()
        suite = race_suite(args.race_repeats) if args.suite=="races" else (
            loader.discover(str(ROOT / "model-gateway"), pattern="test_*.py") if args.suite == "all" else (
            loader.loadTestsFromNames(["test_entry_seal_boundaries", "test_entry_acceptance"]
                                     if args.suite == "boundaries" else ENTRY_MODULES)))
        result = unittest.TextTestRunner(stream=capture, verbosity=2, resultclass=EvidenceResult).run(suite)
    java_ok = None
    java_log = "NOT_RUN (--skip-java)"
    if not args.skip_java:
        try:
            child = subprocess.run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(ROOT / "android-agent-probe/test-core.ps1")], capture_output=True,
                timeout=90)
            java_log = (child.stdout + child.stderr).decode("utf-8", errors="replace")
            java_ok = child.returncode == 0
        except (OSError, subprocess.TimeoutExpired) as error:
            java_ok, java_log = False, type(error).__name__
    summary = readiness(result.wasSuccessful() and not result.skipped, java_ok)
    summary.update(suite=args.suite, pythonMethods=result.testsRun,
        pythonFailures=len(result.failures), pythonErrors=len(result.errors),
        pythonSkipped=len(result.skipped),
        subtestRecords=sum(row["kind"] == "subtest" for row in result.rows),
        javaCore=java_ok, softwareExperimentNotModelAccuracy=True)
    if args.suite=="races":
        summary.update(raceSchedules=len(RACE_METHODS),raceRepeats=args.race_repeats,
                       controlledSchedulesNotIndependentLanguageSamples=True)
    current = freeze_sources(source_paths())
    check_source_identity(summary, frozen, current)
    write_bundle(target, summary, result.rows, capture.getvalue(), java_log, frozen, current)
    print(json.dumps(summary, ensure_ascii=True))
    # 2 means incomplete acceptance, not successful approval to start step two.
    return 1 if summary["localVerdict"] == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
