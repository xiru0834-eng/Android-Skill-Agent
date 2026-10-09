"""Print the actual isolated unittest ledger as JSON; does not write files."""
import json
import sys
import time
import unittest


class Ledger(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.subcases = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.rows.append({'test': test.id(), 'status': 'PASS'})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.rows.append({'test': test.id(), 'status': 'FAIL', 'error': str(err[1])})

    def addError(self, test, err):
        super().addError(test, err)
        self.rows.append({'test': test.id(), 'status': 'ERROR', 'error': str(err[1])})

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        self.subcases.append({'test': subtest.id(), 'status': 'PASS' if err is None else 'FAIL'})


def main():
    start = time.perf_counter()
    result = Ledger()
    unittest.defaultTestLoader.loadTestsFromName('test_contracts').run(result)
    report = {
        'scope': 'P1_2_OFFLINE_CONTRACT_CHECKS_NOT_TASK_EXECUTION',
        'result': 'PASS' if result.wasSuccessful() else 'FAIL',
        'tests_run': result.testsRun,
        'successful_tests': sum(row['status'] == 'PASS' for row in result.rows),
        'failures': len(result.failures), 'errors': len(result.errors),
        'subtests_recorded': len(result.subcases),
        'elapsed_ms': round((time.perf_counter() - start) * 1000, 3),
        'device_tasks': 0, 'device_actions': 0, 'model_calls': 0,
        'product_imports': 0, 'execution_authority': False,
        'cases': result.rows, 'subcases': result.subcases,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
