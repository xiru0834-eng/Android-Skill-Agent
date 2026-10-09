"""Read-only preservation audit plus normal emulator service reconnection."""
import json
import time
from pathlib import Path
from flexible_device_checks import SERIAL, reconnect_experiment_service
from flexible_interruption_checks import oracle, inputs
from named_journey_device import prefs
from transfer_run import private
from workflow_capture import PROBE
from workflow_experiment import write


def main():
    root=Path('output/flexible-workflow-v1')
    out=root/'interruption-v33-preservation-and-idempotence'
    out.mkdir(parents=True,exist_ok=False)
    before=json.loads((root/'interruption-v33-upgrade-preserved/workflow-before.json').read_text(encoding='utf-8'))
    now=prefs(SERIAL)
    keys=['approved','namedSkill','library','name']
    preservation={key:before.get(key)==now.get(key) for key in keys}
    write(out/'workflow-after-matrix.json',now)
    trace=private(SERIAL,PROBE,'workflow-trace.json')
    if trace['end']!='INTERRUPTED':raise RuntimeError('Expected interrupted recording')
    trace_id=trace['traceId']
    names=['workflow-trace.json','workflow-audit-'+trace_id+'.json',
           'workflow-recovery-trace-'+trace_id+'.json',
           'workflow-recovery-trace-'+trace_id+'-original.json']
    original={name:private(SERIAL,PROBE,name) for name in names}
    state=oracle()
    reconnect_experiment_service()
    time.sleep(2)
    after={name:private(SERIAL,PROBE,name) for name in names}
    latest=oracle()
    score=dict(preservation=preservation,checkpointAndDecisionUnchanged=original==after,
               caseUnchanged=state['caseId']==latest['caseId'],
               postReconnectExtraInputs=len(inputs(latest))-len(inputs(state)),
               traceId=trace_id,source='AUTOMATED',modelCalls=0)
    score['assessmentPassed']=(all(preservation.values()) and original==after
        and score['caseUnchanged'] and score['postReconnectExtraInputs']==0)
    write(out/'before.json',original);write(out/'after.json',after)
    write(out/'oracle-before.json',state);write(out/'oracle-after.json',latest)
    write(out/'score.json',score)
    print(json.dumps(score),flush=True)
    if not score['assessmentPassed']:raise SystemExit(1)


if __name__=='__main__':main()
