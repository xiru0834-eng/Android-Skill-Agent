"""Frozen offline batch with a per-case ledger; prints JSON, never device calls."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import unittest
from p14deps import verify_dependencies

BASE = Path(__file__).resolve().parent
GROUPS = ('test_store', 'test_adapter', 'test_hardening', 'test_faults', 'test_cli')
CHANNELS = {'test_store': 'LOCAL_SQLITE_CONTRACT', 'test_adapter': 'LOGIC_SIMULATION_WITH_LOCAL_STORE',
            'test_hardening': 'LOGIC_SIMULATION_SECURITY', 'test_faults': 'REAL_LOCAL_DB_AND_PROCESS_FAULT',
            'test_cli': 'REAL_LOCAL_CLI_SIMULATED_BUSINESS'}


def flatten(suite):
    for case in suite:
        if isinstance(case, unittest.TestSuite):
            yield from flatten(case)
        else:
            yield case


def suite():
    return unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(name) for name in GROUPS)


class Ledger(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.rows, self.subcases = [], []

    def startTest(self, test):
        super().startTest(test)
        self.current = {'test': test.id(), 'channel': CHANNELS[test.id().split('.')[0]], 'status': 'PASS'}
        self.started = time.perf_counter()

    def stopTest(self, test):
        self.current['elapsed_ms'] = round((time.perf_counter() - self.started) * 1000, 3)
        self.rows.append(self.current)
        super().stopTest(test)

    def addFailure(self, test, err):
        self.current.update(status='FAIL', error=str(err[1]))
        super().addFailure(test, err)

    def addError(self, test, err):
        self.current.update(status='ERROR', error=str(err[1]))
        super().addError(test, err)

    def addSubTest(self, test, subtest, err):
        self.subcases.append({'test': subtest.id(), 'status': 'PASS' if err is None else 'FAIL'})
        if err is not None:
            self.current['status'] = 'FAIL'
        super().addSubTest(test, subtest, err)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--freeze', required=True, help='Trusted local, immutable batch manifest')
    args = parser.parse_args(argv)
    freeze = json.loads(Path(args.freeze).read_text(encoding='utf-8'))
    for row in freeze['files']:
        if hashlib.sha256(Path(row['path']).read_bytes()).hexdigest() != row['sha256']:
            print(json.dumps({'result': 'BLOCKED', 'code': 'FROZEN_IMPLEMENTATION_CHANGED', 'path': row['path']}))
            return 2
    selected = suite()
    case_ids = [case.id() for case in flatten(selected)]
    if case_ids != [row['test'] for row in freeze['cases']] or len(case_ids) != len(set(case_ids)):
        print(json.dumps({'result': 'BLOCKED', 'code': 'FROZEN_TEST_MATRIX_CHANGED'}))
        return 2
    result = Ledger()
    selected.run(result)
    report = {'batch': freeze['batch'], 'scope': 'P1_4_OFFLINE_ONLY', 'result': 'PASS' if result.wasSuccessful() else 'FAIL',
              'tests_run': result.testsRun, 'successful_tests': sum(row['status'] == 'PASS' for row in result.rows),
              'subtests_recorded': len(result.subcases), 'failures': len(result.failures), 'errors': len(result.errors),
              'frozen_files_verified': len(freeze['files']), 'p13_modules_pinned': verify_dependencies(),
              'cases': result.rows, 'subcases': result.subcases, 'model_calls': 0, 'device_actions': 0,
              'fixture_assignments_are_device_actions': False, 'device_execution': 'NOT_TESTED',
              'android_transport': 'NOT_CONNECTED', 'execution_authority': False}
    print(json.dumps(report, ensure_ascii=True, allow_nan=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
