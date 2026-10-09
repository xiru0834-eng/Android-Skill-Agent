"""Continue only unattempted entries of a stopped frozen schedule.

The failed attempt stays in results and its raw directory is never written.
This is not a retry policy for the controller or a way to replace failures.
"""
import argparse
import hashlib
import json
from pathlib import Path
from transfer_run import run,approved
from workflow_experiment import write


def resume_boundary(cases,rows):
    if not rows or len(rows)>=len(cases) or 'infrastructureFailure' not in rows[-1]:raise ValueError('Not a stopped incomplete batch')
    if any(row.get('case')!=cases[i] for i,row in enumerate(rows)):raise ValueError('Schedule prefix changed')
    return len(rows)


def checked_diagnosis(diagnosis,failed_case):
    oracle=json.loads((diagnosis/'current-oracle.json').read_text(encoding='utf-8'))
    terminal=json.loads((diagnosis/'latest-result.json').read_text(encoding='utf-8'))
    if oracle.get('caseId')!=failed_case['caseId']:raise ValueError('Diagnosis belongs to another case')
    if terminal.get('status') not in ('SUCCEEDED','UNCONFIRMED','CANCELLED'):raise ValueError('No stopped controller evidence')


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--allow-experiment',action='store_true')
    p.add_argument('--continuation',type=int,choices=range(1,10),default=1);p.add_argument('--diagnosis',type=Path);a=p.parse_args()
    if not a.allow_experiment:p.error('Explicit experiment consent required')
    root=a.directory;load=lambda p:json.loads(p.read_text(encoding='utf-8'))
    protocol=load(root/'protocol.json');rows=load(root/'results.json');cases=protocol['cases'];start=resume_boundary(cases,rows)
    skill=load(root/'skill.json');serial=protocol['device']
    if approved(serial)!=skill:raise ValueError('Approved skill changed')
    label='resume' if a.continuation==1 else f'resume-{a.continuation}'
    if (root/(label+'.json')).exists():raise ValueError('Continuation already used; do not loop')
    if a.continuation>1:
        previous='resume' if a.continuation==2 else f'resume-{a.continuation-1}'
        if not (root/(previous+'.json')).exists() or a.diagnosis is None:raise ValueError('Previous continuation and diagnosis required')
        checked_diagnosis(a.diagnosis,load(root/f'run-{start-1:03d}'/'case.json'))
    if len(list(root.glob('run-*')))!=start:raise ValueError('Unexpected run directories')
    preserved={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for i in range(start) for f in (root/f'run-{i:03d}').rglob('*') if f.is_file()}
    write(root/(label+'.json'),dict(firstUnattemptedIndex=start,failedIndex=start-1,
        diagnosis=str(a.diagnosis) if a.diagnosis else None,
        rule='Keep failure in denominator; no retry of any attempted case; frozen executor and budget unchanged',
        harnessVersion='H3.1',harnessSourceHashes={name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
            for name in ('transfer_run.py','transfer_terminal_wait.py','workflow_capture.py','transfer_input_ready.py')},preservedRawFiles=preserved))
    write(root/('results-before-'+label+'.json'),rows)
    try:
        for index in range(start,len(cases)):
            case=cases[index];directory=root/f'run-{index:03d}'
            try:value=run(serial,case,directory,skill)
            except Exception as error:
                value=dict(case=case,infrastructureFailure=str(error),evidence_complete=False)
                write(directory/'failure.json',value);rows.append(value);write(root/'results.json',rows);raise
            rows.append(value);write(root/'results.json',rows)
            print(json.dumps(dict(index=index,status=value['status'],confirmed=value['confirmed_success'],reason=value['reason'],ms=value['elapsed_ms'])),flush=True)
        summary=dict(planned=len(cases),attempted=len(rows),confirmed=sum(r.get('confirmed_success',False) for r in rows),
            false_success=sum(r.get('false_success',False) for r in rows),unknown=sum(not r.get('evidence_complete',False) for r in rows))
        write(root/'summary.json',summary);print(json.dumps(summary),flush=True)
    finally:
        intact=all(Path(f).is_file() and hashlib.sha256(Path(f).read_bytes()).hexdigest()==h for f,h in preserved.items())
        write(root/(label+'-preservation.json'),dict(unchanged=intact,checkedFiles=len(preserved)))
        if not intact:raise RuntimeError('Prior raw evidence changed')


if __name__=='__main__':main()
