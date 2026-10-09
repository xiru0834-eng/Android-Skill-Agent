"""Sequential fixed normal matrix. Stop on the first failure; never erase a batch."""
import argparse
import json
import random
from pathlib import Path
import task3_device_checks as device
from task3_protocol import FLOWS,cases,summary
from workflow_experiment import write


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    write(out/'device.json',device.gate())
    frozen=device.source_hashes();write(out/'source-hashes.json',frozen)
    plan=[c for c in cases() if c['group'] in ['single','multi']]
    random.Random(300731).shuffle(plan);write(out/'frozen-cases.json',plan)
    existing={'S1':Path('output/autonomous-five/task-3/dev-S1-record-r3/recording'),
              'M6':Path('output/autonomous-five/task-3/dev-M6-review-v39-r2/recording')}
    existing.update({flow:Path('output/autonomous-five/task-3/normal-v39-batch2')/(flow+'-recording') for flow in ['S2','S3','S4','S5']})
    existing.update({flow:Path('output/autonomous-five/task-3/normal-v39-batch3')/(flow+'-recording') for flow in ['M1','M2','M3','M4','M5']})
    # Preserve the failed genuine S6 teaching, rather than inventing its ambiguous save.
    blocked=[dict(id=c['id'],status='BLOCKED',evidenceQualified=False,reason='S6_SOURCE_SAVE_AMBIGUOUS_WITHOUT_STATE_CHANGE',
                  sourceFailure='output/autonomous-five/task-3/normal-v39-batch2/failed-recording-trace.json') for c in plan if c['flow']=='S6']
    rows=list(blocked);skills={};write(out/'rows.json',rows);write(out/'summary.json',summary(rows))
    try:
        # The same real source recording is reused for every initial-state/repeat row.
        for flow in FLOWS:
            if flow=='S6':continue
            if flow in existing:
                source=existing[flow]
                skill=json.loads((source/'skill.json').read_text(encoding='utf-8'))
                trace=json.loads((source/'trace.json').read_text(encoding='utf-8'))
                if device.compile_evidence(trace)!=skill or [s['id'] for s in trace['steps']]!=FLOWS[flow]['actions']:
                    raise RuntimeError('EXISTING_SOURCE_DIFFERS')
                write(out/(flow+'-source.json'),dict(source=str(source),traceId=skill['traceId'],reRecorded=False))
            else:
                source=out/(flow+'-recording')
                skill=device.record(flow,source)
            skills[flow]=skill
        write(out/'skills.json',skills)
        for row in plan:
            if row['flow']=='S6':continue
            value=device.normal(row,skills[row['flow']],out/row['id'])
            rows.append(value);write(out/'rows.json',rows);write(out/'summary.json',summary(rows))
            if value['status']!='PASS':raise RuntimeError('CONFIRMATION_NOT_CORRECT')
    except Exception as error:
        write(out/'failure.json',dict(error=type(error).__name__,reason=str(error),paidCalls=0))
        try:device.snap(device.SERIAL,out/'failure.png')
        except Exception:pass
        raise
    finally:
        write(out/'preparation-reads.json',device.PREPARATION_READS)
        write(out/'source-stability.json',dict(sourceStable=device.source_hashes()==frozen,paidCalls=0))
        write(out/'summary.json',summary(rows))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output)
