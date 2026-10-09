"""Small separately frozen failure suite; not pooled into ordinary success rates."""
import argparse,json
from pathlib import Path
from partial_journey import run
from workflow_experiment import write

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['freeze','run']);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='freeze':
        cases=[]
        for repeat in range(2):
            for fault,key,reason in [('drop','lamp','STEP_UNCONFIRMED'),('duplicate','lamp','AMBIGUOUS:wfLampPower'),('missing','fan','MISSING:wfFanSave')]:
                cases.append(dict(skill=key,condition=fault,fault=fault,repeat=repeat,initial=[0,40,0,3],expected='UNCONFIRMED',expectedReason=reason))
        a.output.mkdir(parents=True,exist_ok=False);write(a.output/'protocol.json',dict(cases=cases,notPooled=True));return
    rows=[]
    for i,case in enumerate(json.loads((a.output/'protocol.json').read_text(encoding='utf-8'))['cases']):
        row=run('R5CW134LLBZ',case,a.output/f'run-{i:03d}')
        row['passFailureCriteria']=row['status']==case['expected'] and row['reason']==case['expectedReason'] and not row['false_success'] and not row['non_target_violation'] and not row['unexpectedInputs'] and not row['afterDeadlineInputs']
        rows.append(row);write(a.output/'results.json',rows);print(json.dumps(dict(index=i,fault=case['fault'],status=row['status'],reason=row['reason'],correctStop=row['passFailureCriteria'])),flush=True)

if __name__=='__main__':main()
