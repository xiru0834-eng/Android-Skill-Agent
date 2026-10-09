"""Offline re-scoring of preserved lab evidence. No device or model calls."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from statistics import median
from flexible_device_checks import score
from workflow_contract import compile_evidence
from workflow_experiment import write


def recheck(batches):
    rows=[];seen=set()
    for batch in batches:
        for protocol_path in sorted(batch.glob('*/protocol.json')):
            folder=protocol_path.parent
            if folder.resolve() in seen:raise ValueError('Duplicate execution evidence')
            seen.add(folder.resolve())
            protocol=json.loads(protocol_path.read_text(encoding='utf-8'))
            recording=batch/(protocol['name']+'-recording')
            paths={name:folder/(name+'.json') for name in ('result','oracle','journal','persistent')}
            paths.update(protocol=protocol_path,trace=recording/'trace.json',skill=recording/'skill.json')
            raw={name:path.read_bytes() for name,path in paths.items()}
            data={name:json.loads(value.decode('utf-8')) for name,value in raw.items()}
            if protocol['modelCalls']!=0:raise ValueError('Unexpected model-call protocol')
            if compile_evidence(data['trace'])!=data['skill']:raise ValueError('Skill differs from trace')
            if data['result']['traceSha256']!=data['skill']['traceSha256']:raise ValueError('Wrong skill executed')
            if data['oracle']['caseId']!=protocol['caseId']:raise ValueError('Wrong oracle case')
            if data['oracle']['initial']!=protocol['initial']:raise ValueError('Wrong oracle initial state')
            committed=list(map(int,data['persistent'].split(',')))
            if committed!=data['oracle']['events'][-1]['saved']:raise ValueError('Persistent state differs')
            if [e['seq'] for e in data['journal']]!=list(range(1,len(data['journal'])+1)):
                raise ValueError('Journal sequence differs')
            judged=score(data['skill'],protocol['initial'],data['result'],data['oracle'],data['journal'])
            category='negative' if '-fault-' in folder.name else ('display' if re.search(r'\d+x\d+',folder.name) else 'normal')
            expected_reason='STEP_UNCONFIRMED' if protocol['fault'] in ('drop','rollback') else 'INVALID_START'
            passed=(judged['status']=='UNCONFIRMED' and judged['reason']==expected_reason and not judged['falseSuccess']) if category=='negative' else judged['correctCompletion']
            rows.append(dict(evidence=str(folder),category=category,name=protocol['name'],initial=protocol['initial'],
                             fault=protocol['fault'],assessmentPassed=passed,**judged,
                             sha256={name:hashlib.sha256(value).hexdigest() for name,value in raw.items()}))
    if not rows:raise ValueError('No preserved execution evidence')
    positive=[r for r in rows if r['category']!='negative'];negative=[r for r in rows if r['category']=='negative']
    return dict(mode='OFFLINE_RECHECK_NOT_NEW_EXECUTIONS',rows=rows,summary=dict(
        total=len(rows),normal=sum(r['category']=='normal' for r in rows),display=sum(r['category']=='display' for r in rows),
        positivePassed=sum(r['assessmentPassed'] for r in positive),negative=len(negative),
        negativePassed=sum(r['assessmentPassed'] for r in negative),falseSuccess=sum(r['falseSuccess'] for r in rows),
        untouchedViolations=sum(not r['untouched'] for r in rows),positiveMinMs=min(r['elapsedMs'] for r in positive),
        positiveMedianMs=median(r['elapsedMs'] for r in positive),positiveMaxMs=max(r['elapsedMs'] for r in positive),
        newDeviceExecutions=0,modelCalls=0),
        evaluatorSha256=hashlib.sha256(Path(__file__).with_name('flexible_device_checks.py').read_bytes()).hexdigest())


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--batch',type=Path,action='append',required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if args.output.exists():raise FileExistsError('Preserve prior assessments; choose a fresh output')
    result=recheck(args.batch);write(args.output,result);print(json.dumps(result['summary']),flush=True)
    if not all(r['assessmentPassed'] for r in result['rows']):raise SystemExit(1)


if __name__=='__main__':main()
