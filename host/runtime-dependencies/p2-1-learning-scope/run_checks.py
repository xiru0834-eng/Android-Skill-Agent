"""Frozen offline verification; stdout evidence, no device/network/model work."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
import unittest

from p21deps import PINS, verify_dependencies

BASE = Path(__file__).resolve().parent
GROUPS = ('test_scope', 'test_budget', 'test_ledger', 'test_review', 'test_sources', 'test_faults', 'test_cli', 'test_runner')
CHANNELS = {'test_scope': 'PURE_LOGIC', 'test_budget': 'LOCAL_ACCOUNTING_SIMULATION',
            'test_ledger': 'REAL_LOCAL_SQLITE', 'test_review': 'LOGIC_AND_LOCAL_STORAGE_REVIEW',
            'test_sources': 'LOCAL_FILES_AND_FILE_FIXTURES', 'test_faults': 'LOCAL_PROCESS_DB_THREAD_FAULTS',
            'test_cli': 'REAL_LOCAL_CLI_NOT_DEVICE', 'test_runner': 'LOCAL_FREEZE_PROTOCOL'}


def flatten(selected):
    for entry in selected:
        if isinstance(entry, unittest.TestSuite):
            yield from flatten(entry)
        else:
            yield entry


def suite():
    return unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(module) for module in GROUPS)


def plan():
    files = [path for path in sorted(BASE.iterdir()) if path.suffix in ('.py', '.json', '.md') and path.is_file()]
    hashes = [{'path': path.as_posix(), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in files]
    hashes.extend(PINS)
    case_ids = [test.id() for test in flatten(suite())]
    return {'batch': 'P2_1_OFFLINE_FROZEN_R1', 'scope': 'P2_1_ONLY_NOT_APP_LEARNING', 'files': hashes,
            'cases': case_ids, 'expected_tests': len(case_ids), 'threshold': 'ALL_APPLICABLE_OFFLINE_CASES_PASS',
            'paid_requests': 0, 'device_actions': 0, 'original_pause_must_remain': True}


class EvidenceResult(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.rows, self.subcases = [], []

    def startTest(self, test):
        super().startTest(test)
        self.current = {'test': test.id(), 'channel': CHANNELS.get(test.id().split('.')[0], 'UNKNOWN'), 'status': 'PASS'}
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

    def addSkip(self, test, reason):
        self.current.update(status='SKIP', error=reason)
        super().addSkip(test, reason)

    def addSubTest(self, test, subtest, err):
        self.subcases.append({'test': subtest.id(), 'status': 'PASS' if err is None else 'FAIL'})
        if err is not None:
            self.current['status'] = 'FAIL'
        super().addSubTest(test, subtest, err)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', action='store_true')
    parser.add_argument('--freeze')
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(plan(), ensure_ascii=True, indent=2))
        return 0
    if not args.freeze:
        parser.error('--freeze is required unless --plan')
    frozen = json.loads(Path(args.freeze).read_text(encoding='utf-8'))
    for file in frozen['files']:
        if not Path(file['path']).is_file() or hashlib.sha256(Path(file['path']).read_bytes()).hexdigest() != file['sha256']:
            print(json.dumps({'result': 'BLOCKED', 'code': 'FROZEN_FILE_CHANGED', 'execution_authority': False}))
            return 2
    selected = suite()
    ids = [test.id() for test in flatten(selected)]
    if ids != frozen['cases'] or len(ids) != len(set(ids)):
        print(json.dumps({'result': 'BLOCKED', 'code': 'FROZEN_TESTS_CHANGED', 'execution_authority': False}))
        return 2
    result = EvidenceResult()
    selected.run(result)
    success = result.wasSuccessful() and not result.skipped
    report = {'batch': frozen['batch'], 'result': 'PASS' if success else 'FAIL', 'tests_run': result.testsRun,
              'passed': sum(row['status'] == 'PASS' for row in result.rows), 'failures': len(result.failures),
              'errors': len(result.errors), 'skipped': len(result.skipped), 'subtests_recorded': len(result.subcases),
              'cases': result.rows, 'subcases': result.subcases,
              'channels': dict(Counter(row['channel'] for row in result.rows)),
              'frozen_files_verified': len(frozen['files']), 'p12_dependencies_verified': verify_dependencies(),
              'real_model_calls': 0, 'device_actions': 0, 'evaluator_device_actions': 0,
              'android_learning': 'NOT_TESTED_NOT_IMPLEMENTED_IN_P2_1', 'execution_authority': False,
              'scope': 'OFFLINE_CONTRACTS_AND_REAL_LOCAL_STORAGE_FILES_CLI_ONLY'}
    print(json.dumps(report, ensure_ascii=True, allow_nan=False, indent=2))
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
