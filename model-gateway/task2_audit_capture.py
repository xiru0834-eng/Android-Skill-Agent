"""Capture existing recorder audit sidecars read-only, after a frozen batch."""
import argparse
import json
from pathlib import Path
from transfer_run import private
from workflow_capture import PROBE
from workflow_experiment import write
from task2_recompute import latency


def metrics(trace,audit):
    if audit.get('traceId')!=trace['traceId'] or audit.get('end')!=trace['end'] or audit.get('error')!=trace['error']:
        raise ValueError('RECORDING_AUDIT_IDENTITY_DIFFERS')
    observations=[e for e in audit['events'] if e.get('kind')=='SETTLE_OBSERVATION']
    confirmed=[e for e in audit['events'] if e.get('kind') in ('CHANGED','NOOP')]
    if [e['step'] for e in confirmed]!=trace['steps']:raise ValueError('RECORDING_AUDIT_STEPS_DIFFER')
    settle=[];previous=None
    for event in audit['events']:
        if event.get('kind')=='SETTLE_OBSERVATION':previous=event
        elif event.get('kind') in ('CHANGED','NOOP'):
            if not previous or previous['decision']!=event['kind']:raise ValueError('CONFIRMATION_TIME_MISSING')
            step=event['step'];when=previous['finishedMs']
            settle.append(dict(id=step['id'],eventTime=step['eventTime'],confirmedElapsedMs=when,
                               uncalibratedClockDifferenceMs=when-step['eventTime']))
    return dict(recordedSteps=len(trace['steps']),confirmedSteps=len(confirmed),auditExact=True,
                confirmations=settle,inputToConfirmation='NOT_MEASURED_CLOCK_DOMAINS_UNCALIBRATED',
                observationCalls=latency([e['elapsedMs'] for e in observations]),
                clocks='eventTime uses uptime; observations use elapsedRealtime. Raw differences are not latency estimates.',
                baselineLatency='NOT_INSTRUMENTED',compileAndStorageNativeLatency='NOT_INSTRUMENTED')


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);rows={}
    for flow in ('P','R','V'):
        trace=json.loads((a.source/(flow+'-recording')/'trace.json').read_text(encoding='utf-8'))
        audit=private('emulator-5554',PROBE,'workflow-audit-'+trace['traceId']+'.json')
        write(a.output/(flow+'-audit.json'),audit);rows[flow]=metrics(trace,audit)
    write(a.output/'metrics.json',rows);print(json.dumps(rows),flush=True)


if __name__=='__main__':main()
