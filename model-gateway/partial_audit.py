"""Recompute partial-workflow scores; correlate journal, actual inputs and private state."""
import argparse,json
from pathlib import Path
from partial_journey import score_case
from transfer_requests import dispatched_requests
from workflow_experiment import write

def load(p):return json.loads(p.read_text(encoding='utf-8'))

def check_run(d,expected_case):
    case,skill,r,o,j=d['case'],d['skill'],d['terminal'],d['oracle'],d['journal']
    if case!=expected_case:raise ValueError('SCHEDULE_CHANGED')
    if r['traceId']!=skill['traceId']:raise ValueError('TRACE_CHANGED')
    if any(e['seq']!=i+1 or e['runId']!=r['runId'] for i,e in enumerate(j)):raise ValueError('JOURNAL_IDENTITY')
    if j[0]['kind']!='START' or j[0]['data']!=skill or j[-1]['kind']!='RESULT' or j[-1]['data']!=r:raise ValueError('JOURNAL_ENDPOINTS')
    score=score_case(case,skill,o,r,d['audit'],j,d['before'])
    if score!=d['score']:raise ValueError('SCORE_CHANGED')
    actual=[e['kind'].split(':',1)[1] for e in o['events'] if e['ms']>=r['startedMs'] and e['kind'].startswith(('input:','edit:'))]
    if dispatched_requests(j,r['actions'])!=actual:raise ValueError('INPUT_LEDGER_MISMATCH')
    passed=score['confirmed_success'] and not score['non_target_violation'] and not score['false_success'] and score['route']['valid'] and not any(score[k] for k in ['extraInputs','unexpectedInputs','afterDeadlineInputs','post_terminal_inputs'])
    if case['condition']=='all':passed=passed and not actual
    return dict(passCriteria=passed,inputLedgerMatch=True,**score)

def audit(root):
    cases=load(root/'protocol.json')['cases'];rows=load(root/'results.json');checks=[]
    if len(cases)!=len(rows):raise ValueError('INCOMPLETE_BATCH')
    for i,case in enumerate(cases):
        d={p.stem:load(p) for p in (root/f'run-{i:03d}').glob('*.json')}
        if d['score']!=rows[i]:raise ValueError('SUMMARY_CHANGED')
        checks.append(check_run(d,case))
    return dict(n=len(checks),passed=sum(c['passCriteria'] for c in checks),falseSuccess=sum(c['false_success'] for c in checks),nonTargetViolations=sum(c['non_target_violation'] for c in checks),checks=checks)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();r=audit(a.directory);write(a.directory/'reaudit.json',r);print(json.dumps({k:v for k,v in r.items() if k!='checks'}))
