"""Re-read every trial; reject missing, stale, unpaired or inconsistent evidence."""
import argparse
import hashlib
import json
from pathlib import Path
from workflow_score import score

def read(path):return json.loads(path.read_text(encoding='utf-8'))

def audit(directory):
    protocol=read(directory/'protocol.json');rows=read(directory/'results.json')
    if len(rows)!=len(protocol['cases']):raise ValueError('Incomplete batch')
    for name,digest in protocol['source_hashes'].items():
        if hashlib.sha256((directory/'sources'/Path(name).name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Snapshot hash mismatch')
    seen=set();pairs={}
    for case,row in zip(protocol['cases'],rows):
        trial=directory/row['run_directory'];stored=read(trial/'case.json')
        result=read(trial/'result.json');oracle=read(trial/'oracle.json');before=read(trial/'before.json')
        for key,value in case.items():
            if row[key]!=value or stored[key]!=value:raise ValueError('Case metadata mismatch')
        nonce=stored['runId']
        if nonce in seen or result['runId']!=nonce or oracle['caseId']!=nonce or before['caseId']!=nonce:
            raise ValueError('Stale/duplicate run identifier')
        seen.add(nonce)
        if result['goal']!=[-1 if x is None else x for x in case['goal']] or result['policy']!=case['policy']:
            raise ValueError('Wrong goal or policy supplied to executor')
        if oracle['initial']!=case['initial'] or before['initial']!=case['initial']:
            raise ValueError('Wrong initialization')
        if oracle['layout']!=case['layout'] or before['layout']!=case['layout']:
            raise ValueError('Wrong layout')
        persisted=trial/'persisted.json'
        if persisted.exists() and read(persisted)!=oracle['events'][-1]['saved']:
            raise ValueError('Persistence mismatch')
        recomputed=score(oracle,result,case['goal'])
        recorded=read(trial/'score.json')
        for key,value in recomputed.items():
            if recorded[key]!=value or row[key]!=value:raise ValueError('Scoring mismatch: '+key)
        pairs.setdefault(case['pair'],[]).append(case)
    for pair in pairs.values():
        if len(pair)!=2 or {r['policy'] for r in pair}!={'R1','P'}:raise ValueError('Unpaired cases')
        for key in ('goal','initial','layout','fault'):
            if pair[0][key]!=pair[1][key]:raise ValueError('Pair mismatch')
    return dict(status='PASS',runs=len(rows),paired_instances=len(pairs),
        persisted_checks=sum((directory/r['run_directory']/'persisted.json').exists() for r in rows),
        false_success=sum(r['false_success'] for r in rows),expected_behavior=sum(r['expected_behavior'] for r in rows))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);p.add_argument('--output',type=Path)
    args=p.parse_args();result=audit(args.directory)
    if args.output:
        with args.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result))
