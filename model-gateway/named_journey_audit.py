"""Re-score named journeys from independent App state, requests and terminal logs."""
import argparse
import json
from pathlib import Path
from transfer_audit import evaluate
from transfer_requests import dispatched_requests
from recovery_evidence import audit_route
from startup_audit import input_safety
from workflow_experiment import write

def load(p):return json.loads(p.read_text(encoding='utf-8'))

def check_run(d,expected_case):
    case,skill,r,o,j=d['case'],d['skill'],d['terminal'],d['oracle'],d['journal']
    if case!=expected_case or d['score']['case']!=case:raise ValueError('SCHEDULE_CHANGED')
    if r['traceId']!=skill['traceId'] or r['traceSha256']!=skill['traceSha256'] or r['goal']!=skill['finalGoals']:raise ValueError('SKILL_CHANGED')
    if o['caseId']!=d['before']['caseId'] or o['initial']!=case['initial'] or o['fault']!=case['fault']:raise ValueError('FIXTURE_CHANGED')
    score=evaluate(o,r,skill['finalGoals'],d['audit'],case_id=d['before']['caseId'],run_id=r['runId'])
    if any(d['score'][k]!=v for k,v in score.items()):raise ValueError('SCORE_MISMATCH')
    if any(row['seq']!=n+1 or row['runId']!=r['runId'] for n,row in enumerate(j)):raise ValueError('JOURNAL_IDENTITY')
    if j[0]['kind']!='START' or j[0]['data']!=skill or j[-1]['kind']!='RESULT' or j[-1]['data']!=r:raise ValueError('JOURNAL_ENDPOINTS')
    requests=dispatched_requests(j,r['actions'])
    actual=[e for e in o['events'] if e['ms']>=r['startedMs'] and e['kind'].startswith(('input:','edit:'))]
    if requests!=[e['kind'].split(':',1)[1] for e in actual]:raise ValueError('INPUT_LEDGER_MISMATCH')
    route=audit_route(r,skill);safety=input_safety(o,r,skill)
    if d['score']['route']!=route or d['score']['inputSafety']!=safety:raise ValueError('SAFETY_MISMATCH')
    if list(map(int,d['persisted'].split(',')))!=o['events'][-1]['saved']:raise ValueError('PERSISTENCE_MISMATCH')
    passed=score['actual_success'] and score['confirmed_success'] and not score['false_success'] and route['valid'] and not any(safety.values()) and score['post_terminal_inputs']==0
    if case['condition']=='all':passed=passed and not requests
    return dict(passCriteria=passed,inputLedgerMatch=True,**score)

def audit(root):
    protocol=load(root/'protocol.json');rows=load(root/'results.json');checks=[]
    if len(rows)!=len(protocol['cases']):raise ValueError('INCOMPLETE_BATCH')
    for i,case in enumerate(protocol['cases']):
        folder=root/f'run-{i:03d}';d={p.stem:load(p) for p in folder.glob('*.json')}
        if d['score']!=rows[i]:raise ValueError('SUMMARY_ROW_MISMATCH')
        checks.append(check_run(d,case))
    return dict(n=len(checks),passed=sum(c['passCriteria'] for c in checks),actual=sum(c['actual_success'] for c in checks),
        falseSuccess=sum(c['false_success'] for c in checks),checks=checks)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();result=audit(a.directory)
    write(a.directory/'reaudit.json',result);print(json.dumps({k:v for k,v in result.items() if k!='checks'}))
