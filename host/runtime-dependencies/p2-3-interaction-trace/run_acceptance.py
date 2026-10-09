"""Frozen, offline-only acceptance runner. JSON stdout; never resumes devices or calls models."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import time
import unittest

def flatten(suite):
    for item in suite:
        if isinstance(item,unittest.TestSuite):yield from flatten(item)
        else:yield item

class Result(unittest.TextTestResult):
    def __init__(self,*args):
        super().__init__(*args)
        self.cases=[]
    def addSuccess(self,test):
        super().addSuccess(test);self.cases.append({'id':test.id(),'result':'PASS'})
    def addFailure(self,test,error):
        super().addFailure(test,error);self.cases.append({'id':test.id(),'result':'FAIL'})
    def addError(self,test,error):
        super().addError(test,error);self.cases.append({'id':test.id(),'result':'ERROR'})
    def addSkip(self,test,reason):
        super().addSkip(test,reason);self.cases.append({'id':test.id(),'result':'NOT_TESTED'})

def main():
    p=argparse.ArgumentParser();p.add_argument('--freeze',required=True,type=Path)
    args=p.parse_args()
    freeze=json.loads(args.freeze.read_text(encoding='utf-8'))
    changed=[]
    for item in freeze['files']:
        path=Path(item['path'])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
            changed.append(item['path'])
    if changed:
        print(json.dumps({'status':'FROZEN_INPUT_DRIFT','changed':changed,'tested':0,'native_actions':0}))
        return 2
    suite=unittest.defaultTestLoader.discover(str(Path(__file__).parent),pattern='test_*.py')
    ids=sorted(t.id() for t in flatten(suite))
    if ids!=freeze['case_ids']:
        print(json.dumps({'status':'CASE_MANIFEST_DRIFT','tested':0,'native_actions':0}))
        return 2
    stream=io.StringIO()
    started=time.perf_counter()
    result=unittest.TextTestRunner(stream=stream,verbosity=2,resultclass=Result).run(suite)
    elapsed=(time.perf_counter()-started)*1000
    groups={}
    for c in result.cases:
        group=c['id'].split('.')[0]
        row=groups.setdefault(group,{'methods':0,'pass':0,'fail':0,'error':0})
        row['methods']+=1;row[c['result'].lower()]+=1
    report={'batch_id':freeze['batch_id'],'status':'OFFLINE_PASS' if result.wasSuccessful() else 'OFFLINE_FAIL',
            'channel':'OFFLINE_CONTROLLED_TRAJECTORY_AND_LOCAL_STORAGE',
            'methods_run':result.testsRun,'cases':result.cases,'groups':groups,
            'failures':len(result.failures),'errors':len(result.errors),'duration_ms':round(elapsed,3),
            'native_actions':0,'paid_model_requests':0,'real_android_e2e':'BLOCKED',
            'real_verified_edges':0,'full_p23':'PARTIAL','p24_started':False,
            'frozen_files_checked':len(freeze['files']),'frozen_drift':changed,'raw_test_output':stream.getvalue()}
    print(json.dumps(report,ensure_ascii=False,sort_keys=True))
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':
    raise SystemExit(main())
