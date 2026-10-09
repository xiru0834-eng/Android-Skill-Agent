"""Recompute results and match requested inputs against independent App events."""
import argparse
import hashlib
import json
from pathlib import Path
from transfer_audit import evaluate
from transfer_requests import dispatched_requests
from workflow_experiment import write

def load(p):return json.loads(p.read_text(encoding='utf-8'))

def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();root=a.directory
    protocol=load(root/'protocol.json');skill=load(root/'skill.json');rows=[]
    for folder in sorted(root.glob('run-*')):
        if not (folder/'score.json').exists():
            rows.append(dict(run=folder.name,auditable=False,reason='NO_SCORE'));continue
        case=load(folder/'case.json');result=load(folder/'terminal.json');oracle=load(folder/'oracle.json');audits=load(folder/'audit.json')
        judged=evaluate(oracle,result,skill['finalGoals'],audits,case_id=case['caseId'],run_id=result['runId'])
        recorded=load(folder/'score.json')
        for key,value in judged.items():
            if recorded[key]!=value:raise ValueError('Score mismatch: '+folder.name+'/'+key)
        journal=load(folder/'journal.json')
        if not all(j['seq']==i+1 and j['runId']==result['runId'] for i,j in enumerate(journal)):raise ValueError('Journal correlation')
        requests=dispatched_requests(journal,result['actions'])
        actual=[e for e in oracle['events'] if e['ms']>=result['startedMs'] and e['kind'].startswith(('input:','edit:'))]
        accepted=[e['kind'].split(':',1)[1] for e in actual]
        late=[e for e in actual if e['ms']>result['finishedMs']]
        final_ms=journal[-1]['ms']
        if journal[-1]['kind']!='RESULT' or journal[-1]['data']['status']!=result['status']:raise ValueError('Missing terminal journal')
        rows.append(dict(run=folder.name,auditable=True,confirmed=judged['confirmed_success'],false_success=judged['false_success'],
             actualInputsMatchRequested=accepted==requests,lateAppInputs=len(late),journalComplete=True,elapsedMs=judged['elapsed_ms']))
    result=dict(planned=len(protocol['cases']),recorded=len(rows),rows=rows,
        complete=len(rows)==len(protocol['cases']) and all(r['auditable'] for r in rows))
    write(root/'reaudit.json',result)
    print(json.dumps(dict(planned=result['planned'],recorded=result['recorded'],complete=result['complete'],
          confirmed=sum(r.get('confirmed',False) for r in rows),false_success=sum(r.get('false_success',False) for r in rows),
          unknown=sum(not r['auditable'] for r in rows),
          inputMismatch=sum(r['auditable'] and not r['actualInputsMatchRequested'] for r in rows),lateAppInputs=sum(r.get('lateAppInputs',0) for r in rows))))

if __name__=='__main__':main()
