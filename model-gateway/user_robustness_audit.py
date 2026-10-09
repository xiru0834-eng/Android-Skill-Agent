"""Offline replay using independent App ledger; does not contact a device."""
import argparse
import json
from pathlib import Path
from transfer_audit import evaluate
from transfer_requests import dispatched_requests
from recovery_evidence import audit_route
from startup_audit import input_safety
from user_robustness import expectation,summary
from workflow_experiment import write

def load(p):return json.loads(p.read_text(encoding='utf-8'))

def audit(root):
    root=Path(root);protocol=load(root/'protocol.json');skill=load(root/'skill.json');rows=load(root/'results.json')
    if len(rows)>len(protocol['cases']):raise ValueError('EXTRA_TRIALS')
    checks=[]
    for i,row in enumerate(rows):
        if row['case']!=protocol['cases'][i]:raise ValueError('SCHEDULE_CHANGED')
        if not row.get('evidence_complete'):
            checks.append(dict(index=i,auditable=False));continue
        folder=root/f'run-{i:03d}'
        case,result,oracle,audits,journal=[load(folder/name) for name in ('case.json','terminal.json','oracle.json','audit.json','journal.json')]
        if any(case[k]!=v for k,v in row['case'].items()):raise ValueError('CASE_CHANGED')
        if result['traceId']!=skill['traceId'] or result['traceSha256']!=skill['traceSha256'] or result['goal']!=skill['finalGoals']:raise ValueError('SKILL_CHANGED')
        if oracle['initial']!=case['initial'] or oracle['fault']!=case['fault']:raise ValueError('WRONG_INITIAL_OR_FAULT')
        score=evaluate(oracle,result,skill['finalGoals'],audits,case_id=case['caseId'],run_id=result['runId'])
        if any(row[k]!=v for k,v in score.items()):raise ValueError('SCORE_MISMATCH')
        if any(j['seq']!=n+1 or j['runId']!=result['runId'] for n,j in enumerate(journal)):raise ValueError('JOURNAL_IDENTITY')
        if journal[-1]['kind']!='RESULT' or journal[-1]['data']!=result:raise ValueError('TERMINAL_JOURNAL')
        actual=[e for e in oracle['events'] if e['ms']>=result['startedMs'] and e['kind'].startswith(('input:','edit:'))]
        requests=dispatched_requests(journal,result['actions'])
        route=audit_route(result,skill);safety=input_safety(oracle,result,skill)
        if row['route']!=route or row['inputSafety']!=safety:raise ValueError('SAFETY_SCORE_MISMATCH')
        if row['expectedBehavior']!=expectation(row,row['case'],route['valid'],safety):raise ValueError('EXPECTATION_MISMATCH')
        persisted=[int(v) for v in load(folder/'persisted.json').split(',')]
        if persisted!=oracle['events'][-1]['saved']:raise ValueError('PERSISTENCE_MISMATCH')
        checks.append(dict(index=i,auditable=True,inputLedgerMatch=requests==[e['kind'].split(':',1)[1] for e in actual],
            lateInputs=sum(e['ms']>result['finishedMs'] for e in actual)))
    recomputed=summary(rows,len(protocol['cases']))
    return dict(summary=recomputed,rows=checks,inputMismatch=sum(r.get('inputLedgerMatch') is False for r in checks),
        lateInputs=sum(r.get('lateInputs',0) for r in checks))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args()
    report=audit(a.directory);write(a.directory/'reaudit.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='rows'}))
