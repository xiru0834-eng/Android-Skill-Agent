"""Isolated process ledger over real existing test entry points; never a model tool."""
import argparse
import json
from pathlib import Path
import sys
import time
import traceback
import unittest


def flatten(suite):
    for value in suite:
        if isinstance(value, unittest.TestSuite):
            yield from flatten(value)
        else:
            yield value


class Ledger(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.rows, self.subcases = [], []

    def startTest(self, test):
        super().startTest(test)
        self.row = {"case_id": test.id(), "result": "PASS", "evidence_channel": "PURE_CONTRACT_OR_LOCAL_TEST"}
        self.started = time.perf_counter()

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.row.update(result="FAIL", error="".join(traceback.format_exception(*err)))

    def addError(self, test, err):
        super().addError(test, err)
        self.row.update(result="ERROR", error="".join(traceback.format_exception(*err)))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.row.update(result="NOT_TESTED", reason=reason)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        row = {"parent_case_id": test.id(), "case_id": subtest.id(), "result": "PASS" if err is None else "FAIL"}
        if err:
            row["error"] = "".join(traceback.format_exception(*err))
            self.row["result"] = "FAIL"
        self.subcases.append(row)

    def stopTest(self, test):
        self.row["latency_ms"] = round((time.perf_counter() - self.started) * 1000, 3)
        self.rows.append(self.row)
        super().stopTest(test)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--catalog", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.directory.resolve()))
    suite = unittest.defaultTestLoader.discover(str(args.directory), pattern="test_*.py")
    cases = [{"case_id": case.id(), "source_path": str(args.directory / (case.__class__.__module__ + ".py"))} for case in flatten(suite)]
    if args.catalog:
        out = {"cases": cases, "count": len(cases), "status": "PLANNED_NOT_EXECUTED"}
    else:
        ledger = Ledger()
        suite.run(ledger)
        out = {"cases": ledger.rows, "subcases": ledger.subcases, "count": ledger.testsRun,
               "correct": sum(row["result"] == "PASS" for row in ledger.rows),
               "status": "PASS" if ledger.wasSuccessful() and not ledger.skipped else "FAIL",
               "model_calls": 0, "not_android_execution": True}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise RuntimeError("OUTPUT_EXISTS_PRESERVE_PREVIOUS_RUN")
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: out[key] for key in ("count", "status")} | {"output": str(args.output)}))
    return 0 if out["status"] != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
