"""Evaluator-only cancellation boundaries using actual service and delayed target commit."""
import argparse,copy,json,time,uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from lab_transport import adb,execute,cancel
from g1_device_eval import prepare,oracle
from install_candidate import health
from prepare_g1 import save
ROOT=Path(__file__).parent

def run(host,out):
    out.mkdir(parents=True,exist_ok=False)
    base=json.loads((ROOT/'evidence'/host/'g1-plan.json').read_text(encoding='utf-8'))
    save(out/'registered.json',{'cases':['cancel_after_issued_before_receipt','cancel_after_receipt'],
        'channel':'STRUCTURED_CANCELLATION_SUPPLEMENT','model_calls':0,'issued_action_may_commit_after_cancel':True})
    rows=[]
    for name in ('cancel_after_issued_before_receipt','cancel_after_receipt'):
        plan=copy.deepcopy(base);plan['task_id']='task.'+uuid.uuid4().hex
        before=prepare(host,uuid.uuid4().hex,(0,50,0,22),delay=2000 if name.endswith('before_receipt') else 0)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(execute,host,plan);until=time.monotonic()+12;witness=None
            while name.endswith('before_receipt') and time.monotonic()<until and not future.done():
                current=oracle(host)
                if current['requests']:witness=current;break
                time.sleep(.08)
            if name.endswith('before_receipt'):
                if not witness:raise ValueError('NO_PRE_RECEIPT_ISSUED_ACTION_WITNESS')
                issued_before_receipt=not future.done();cancel(host);result=future.result(timeout=15)
            else:
                result=future.result(timeout=15);issued_before_receipt=None;cancel(host)
        time.sleep(2.5) # Target's declared 2s commit may finish; never rollback.
        after=oracle(host);ready=health(host)
        wanted=dict(before['state']);wanted['bedroom_light.brightnessPercent']=80
        writes=[(e['property'],e['value']) for e in after['requests']]
        events=[(e['property'],e['value']) for e in after['events']]
        # The unchanged target journals requests only for deferred commits;
        # immediate commits expose the action in events, not in requests.
        expected_requests=[('bedroom_light.brightnessPercent',80)] if name.endswith('before_receipt') else []
        correct=writes==expected_requests and events==[('bedroom_light.brightnessPercent',80)] and after['state']==wanted
        if name.endswith('before_receipt'):
            outcome=issued_before_receipt and result.get('final_status')=='CANCELLED' and result.get('verification_result') is False
        else:
            raw=adb(host,'exec-out','run-as','edu.sydney.probe','cat','files/flow-audit-'+result['request_id']+'.json')
            stored=json.loads(raw)
            outcome=result.get('final_status')=='SUCCESS' and stored.get('final_status')=='SUCCESS' and stored.get('verification_result') is True
        row={'case':name,'host':host,'before':before,'plan':plan,'issued_witness':witness,'issued_before_receipt':issued_before_receipt,
            'result':result,'after':after,'health_after':ready,'no_extra_input_after_cancel':writes==expected_requests and len(events)==1,
            'already_issued_delayed_commit_recorded':name.endswith('before_receipt') and after['state']==wanted,
            'passed':bool(outcome and correct and ready.get('final_status')=='READY' and not ready.get('busy'))}
        rows.append(row);save(out/(name+'.json'),row);print(name,row['passed'],result.get('final_status'),flush=True)
        if not correct:raise ValueError('SAFETY_STOP')
    save(out/'summary.json',{'passed':sum(r['passed'] for r in rows),'planned':2,'executed':len(rows),'model_calls':0})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.host,a.out)
