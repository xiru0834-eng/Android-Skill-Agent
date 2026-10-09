"""Run isolated contract/check tests and print the actual JSON case ledger."""
import json
import sys
import time
import unittest
from dependencies import verify_dependencies


class Ledger(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.rows, self.subcases = [], []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.rows.append(dict(test=test.id(), status='PASS'))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.rows.append(dict(test=test.id(), status='FAIL', error=str(err[1])))

    def addError(self, test, err):
        super().addError(test, err)
        self.rows.append(dict(test=test.id(), status='ERROR', error=str(err[1])))

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        self.subcases.append(dict(test=subtest.id(), status='PASS' if err is None else 'FAIL'))


def main():
    start = time.perf_counter()
    verified = verify_dependencies()
    result = Ledger()
    for name in ('test_compiler', 'test_checks', 'test_cursor', 'test_delivery'):
        unittest.defaultTestLoader.loadTestsFromName(name).run(result)
    report = dict(scope='P1_3_OFFLINE_COMPILER_AND_CHECKS_NOT_DEVICE_EXECUTION',
                  result='PASS' if result.wasSuccessful() else 'FAIL',
                  tests_run=result.testsRun,
                  successful_tests=sum(row['status'] == 'PASS' for row in result.rows),
                  failures=len(result.failures), errors=len(result.errors),
                  subtests_recorded=len(result.subcases),
                  pinned_dependencies_verified=verified,
                  elapsed_ms=round((time.perf_counter() - start) * 1000, 3),
                  device_tasks=0, device_actions=0, model_calls=0,
                  fixture_state_assignments_are_device_actions=False,
                  execution_authority=False, cases=result.rows, subcases=result.subcases)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
