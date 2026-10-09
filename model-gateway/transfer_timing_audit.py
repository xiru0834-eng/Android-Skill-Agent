"""Read-only v3 timing assertions. Does not repair or replace primary scores."""
import argparse
import json
from pathlib import Path
from workflow_experiment import write


def inspect_timing(result,journal):
    deadline=result['deadlineMs'];actions=result['actions'];errors=[]
    returned=[e['data'] for e in journal if e['kind']=='INPUT_RETURN']
    if len(returned)!=len(actions):errors.append('DISPATCH_EVIDENCE_INCOMPLETE')
    if result['status']=='SUCCEEDED' and result['finishedMs']>=deadline:errors.append('LATE_SUCCESS')
    for action in actions:
        if action['ms']>=deadline:errors.append('INPUT_AT_OR_AFTER_DEADLINE')
    for action,row in zip(actions,returned):
        dispatched=row.get('dispatchedMs');window=row.get('confirmationDeadlineMs')
        if dispatched!=action['ms']:errors.append('DISPATCH_CLOCK_MISMATCH')
        if dispatched is None or window!=min(dispatched+3000,deadline):errors.append('WRONG_CONFIRMATION_WINDOW')
    return dict(passes=not errors,errors=errors,inputs=len(actions),
        abortedRequests=sum(e['kind']=='INPUT_ABORTED' for e in journal),
        lastInputRemainingMs=deadline-actions[-1]['ms'] if actions else None)


def main():
    p=argparse.ArgumentParser();p.add_argument('batches',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Refuse overwrite')
    rows=[]
    for batch in a.batches:
        for run in sorted(batch.glob('run-*')):
            if not (run/'score.json').exists():rows.append(dict(run=str(run),passes=None,errors=['NO_COMPLETE_SCORE']));continue
            result=json.loads((run/'terminal.json').read_text(encoding='utf-8'));journal=json.loads((run/'journal.json').read_text(encoding='utf-8'))
            rows.append(dict(run=str(run),**inspect_timing(result,journal)))
    value=dict(rows=rows,passed=sum(r['passes'] is True for r in rows),failed=sum(r['passes'] is False for r in rows),unknown=sum(r['passes'] is None for r in rows))
    write(a.output,value);print(json.dumps({k:v for k,v in value.items() if k!='rows'}))


if __name__=='__main__':main()
