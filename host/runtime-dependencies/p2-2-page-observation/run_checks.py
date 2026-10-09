"""Frozen P2.2 offline verification. Does not invoke Android, network or models."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time
import unittest
from p22deps import PINS, verify_dependencies

BASE = Path(__file__).resolve().parent
GROUPS = ('test_tree','test_capture','test_contract','test_identity','test_store','test_cli',
          'test_adapter_boundary','test_dataset','test_runner')
CHANNELS = {'test_tree':'PURE_DTO','test_capture':'OFFLINE_CALLBACK_SIMULATION','test_contract':'SERIALIZED_CONTRACT',
            'test_identity':'PURE_IDENTITY_AND_INDEX','test_store':'REAL_LOCAL_SQLITE',
            'test_cli':'REAL_LOCAL_CLI_NOT_DEVICE','test_adapter_boundary':'STATIC_SOURCE_ONLY',
            'test_dataset':'LABELED_SYNTHETIC_DTO','test_runner':'LOCAL_FREEZE_PROTOCOL'}
BOUNDARY = {'batch':'P2_2_OFFLINE_FROZEN_R2','threshold':'ALL_APPLICABLE_OFFLINE_CASES_PASS',
            'model_calls':0,'device_actions':0,'evaluator_device_actions':0,'original_pause_must_remain':True,
            'scope':'P2_2_OBSERVATION_IDENTITY_INDEX_ONLY','native_capture':'NOT_TESTED_NOT_WIRED'}
CONFIGURATION = {'total_ms':2000,'pair_ms':250,'max_attempts':2,'max_nodes':2048,'max_depth':64,
                 'max_text_chars':256,'max_query_limit':100,'entity_rule':'PUBLIC_TYPED_HEADING_PREFIX_V1'}


def inputs():
    files = [p for p in BASE.iterdir() if p.is_file() and (p.suffix in ('.py','.ps1') or p.name in
             ('dependency-pins.json','DESIGN.md','README.md','API.md'))]
    files += list((BASE / 'native').rglob('*.java'))
    files += [Path(item['path']) for item in PINS]
    return [{'path':p.as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in sorted(set(files))]


def flatten(selected):
    for item in selected:
        if isinstance(item,unittest.TestSuite): yield from flatten(item)
        else: yield item


def suite():
    return unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(module) for module in GROUPS)


def plan():
    cases = [test.id() for test in flatten(suite())]
    return dict(BOUNDARY,files=inputs(),cases=cases,expected_tests=len(cases),configuration=CONFIGURATION.copy())


def check_freeze(frozen):
    if type(frozen) is not dict or any(frozen.get(k) != v for k,v in BOUNDARY.items()) or frozen.get('configuration') != CONFIGURATION:
        raise ValueError('FROZEN_BOUNDARY_CHANGED')
    current = inputs(); provided = frozen.get('files',[])
    if type(provided) is not list or [f.get('path') for f in provided] != [f['path'] for f in current]:
        raise ValueError('FROZEN_INVENTORY_CHANGED')
    if any(a.get('sha256') != b['sha256'] for a,b in zip(provided,current)):
        raise ValueError('FROZEN_FILE_CHANGED')
    # Hash/inventory checks happen before loading the test modules on a formal run.
    actual = [test.id() for test in flatten(suite())]
    if frozen.get('cases') != actual or frozen.get('expected_tests') != len(actual) or len(actual) != len(set(actual)):
        raise ValueError('FROZEN_TESTS_CHANGED')


class EvidenceResult(unittest.TestResult):
    def __init__(self):
        super().__init__(); self.rows = []; self.subcases = []
    def startTest(self,test):
        super().startTest(test)
        self.current = {'test':test.id(),'channel':CHANNELS.get(test.id().split('.')[0],'UNKNOWN'),'status':'PASS'}
        self.started = time.perf_counter()
    def stopTest(self,test):
        self.current['elapsed_ms'] = round((time.perf_counter()-self.started)*1000,3)
        self.rows.append(self.current); super().stopTest(test)
    def addFailure(self,test,err):
        self.current.update(status='FAIL',code=type(err[1]).__name__); super().addFailure(test,err)
    def addError(self,test,err):
        self.current.update(status='ERROR',code=type(err[1]).__name__); super().addError(test,err)
    def addSkip(self,test,reason):
        self.current.update(status='SKIP'); super().addSkip(test,reason)
    def addSubTest(self,test,subtest,err):
        self.subcases.append({'test':subtest.id(),'status':'PASS' if err is None else 'FAIL'})
        if err is not None: self.current['status'] = 'FAIL'
        super().addSubTest(test,subtest,err)


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--plan',action='store_true'); parser.add_argument('--freeze')
    args = parser.parse_args()
    if args.plan:
        print(json.dumps(plan(),ensure_ascii=True,indent=2)); return 0
    if not args.freeze: parser.error('--freeze is required')
    try:
        frozen = json.loads(Path(args.freeze).read_text(encoding='utf-8')); check_freeze(frozen)
    except (ValueError,OSError,TypeError,KeyError):
        print(json.dumps({'result':'BLOCKED','code':'FROZEN_INPUT_INVALID_OR_CHANGED','execution_authority':False})); return 2
    selected = suite(); result = EvidenceResult(); selected.run(result)
    okay = result.wasSuccessful() and not result.skipped
    report = {'batch':frozen['batch'],'result':'PASS' if okay else 'FAIL','scope':frozen['scope'],
              'tests_run':result.testsRun,'passed':sum(row['status']=='PASS' for row in result.rows),
              'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
              'cases':result.rows,'subcases':result.subcases,'subtests_recorded':len(result.subcases),
              'channels':dict(Counter(row['channel'] for row in result.rows)),
              'frozen_files_verified':len(frozen['files']),'p21_dependencies_verified':verify_dependencies(),
              'model_calls':0,'device_actions':0,'evaluator_device_actions':0,
              'android_runtime':'NOT_TESTED_NOT_WIRED','execution_authority':False}
    print(json.dumps(report,ensure_ascii=True,allow_nan=False,indent=2))
    return 0 if okay else 1


if __name__ == '__main__': raise SystemExit(main())
