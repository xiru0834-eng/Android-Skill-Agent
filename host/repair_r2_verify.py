"""Isolated continuation tests. Never modifies sealed r1 or the published capsule."""
import argparse
import json
from pathlib import Path
from repair_r2 import prepare_current
from prepare_g1 import save

ROOT = Path(__file__).parent
RUN = ROOT/'evidence/flow-deadline-repair/r2'
LABEL = 'v102'

def guarded_assessment(original):
    def check(result,*args):
        assessed=original(result,*args)
        if result.get('final_status') in {'SUCCESS','NO_ACTION_REQUIRED'}:
            full=(result.get('final_observation_complete') is True and result.get('verification_result') is True
                  and all(s.get('status')=='VERIFIED' for s in result.get('steps',[]))
                  and result.get('latency',{}).get('runtime_ms',999999)<8000)
            if not full:
                assessed=dict(assessed,passed=False,false_success=True,completion_contract_failed=True)
        return assessed
    return check

def devices():
    import g1_device_eval as g1
    import repair_cancel_eval as cancellation
    g1.prepare = prepare_current
    g1.assess = guarded_assessment(g1.assess)
    cancellation.prepare = prepare_current
    for host in ('emulator-5556','R5CW134LLBZ'):
        folder=RUN/'regression'/(LABEL+'-g1-'+host)
        g1.run(host, folder)
        summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
        if summary['wrong_action'] or summary['false_success']:raise ValueError('SAFETY_STOP')
        cancellation.run(host, RUN/'regression'/(LABEL+'-cancel-'+host))

def validation():
    import g2_validate_publish as g2
    g2.prepare = prepare_current
    # A separate evaluation library/revision: original formal package is immutable.
    g2.run(RUN/'validation-refresh'/(LABEL+'-phone'), ROOT/'private/flow-deadline-repair-r2'/('validation-library-'+LABEL))

def local():
    import verify_regression
    import subprocess, sys, hashlib
    out = RUN/'regression'/(LABEL+'-local')
    passed = verify_regression.run(out)
    command = [sys.executable,'-m','unittest','test_repair_scorer','-v']
    result = subprocess.run(command,cwd=ROOT,capture_output=True,timeout=60)
    raw=result.stdout+b'\n'+result.stderr
    (out/'scorer.log').write_bytes(raw)
    save(out/'scorer.json',{'command':command,'exit_code':result.returncode,
         'passed':result.returncode==0,'log_sha256':hashlib.sha256(raw).hexdigest(),
         'channel':'SYNTHETIC_SCORER_SELF_TEST','real_android_cases':0,'model_calls':0})
    if not passed or result.returncode: raise ValueError('LOCAL_REGRESSION_FAILED')

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('operation',choices=['devices','validation','local'])
    parser.add_argument('--label',default=LABEL)
    args=parser.parse_args()
    LABEL=args.label
    globals()[args.operation]()
