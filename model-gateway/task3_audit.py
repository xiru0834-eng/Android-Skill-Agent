"""Independent raw-file re-audit. No device inputs and no overwriting capture scores."""
import argparse
import hashlib
import json
import math
from pathlib import Path
from flexible_device_checks import expected_process_states
from task3_protocol import judge,summary,cases
from workflow_experiment import write


def audit_envelope(result,oracle,samples):
    errors=[]
    def check(ok,reason):
        if not ok:errors.append(reason)
    try:
        check(all(type(result[k]) is int for k in ['startedMs','finishedMs','deadlineMs']),'RESULT_CLOCK_TYPES')
        check(all(type(e['ms']) is int and type(e['pending']) is int and e['pending'] in [0,1] for e in oracle['events']),'ORACLE_VALUE_TYPES')
        check(len(samples)==3,'THREE_FRESH_AUDITS_REQUIRED');last_ms=result['finishedMs'];last_size=0
        for audit in samples:
            event=audit['events'][-1];at=event['ms']
            check(event['kind']=='audit_snapshot' and at>=last_ms and len(audit['events'])>last_size,'FRESH_AUDIT_IDENTITY')
            check(audit['events']==oracle['events'][:len(audit['events'])],'AUDIT_LEDGER_PREFIX_REWRITTEN')
            last_ms=at;last_size=len(audit['events'])
        check(samples[-1]==oracle and last_ms-result['finishedMs']>=5000,'AUDIT_WINDOW_INCOMPLETE')
        check(all(a['ms']<=b['ms'] for a,b in zip(oracle['events'],oracle['events'][1:])),'ORACLE_CLOCK_REVERSED')
    except (KeyError,TypeError,IndexError,ValueError):errors.append('INCOMPLETE_AUDIT_ENVELOPE')
    return errors


def identity_types(result,journal):
    try:
        valid=(isinstance(result['runId'],str) and bool(result['runId'])
               and all(type(result[k]) is int for k in ['completedSteps','terminalStepIndex'])
               and all(type(e[k]) is int for e in journal for k in ['seq','ms','stepIndex','phase'])
               and all(type(a[k]) is int for a in result['actions'] for k in ['ms','sourceIndex']))
        return [] if valid else ['JOURNAL_OR_RESULT_TYPES']
    except (KeyError,TypeError):return ['JOURNAL_OR_RESULT_TYPES']


def rejudge(skill,initial,result,oracle,journal,samples,disk,case_id):
    base=judge(skill,initial,result,oracle,journal,samples,disk,case_id)
    envelope=audit_envelope(result,oracle,samples)+identity_types(result,journal);errors=list(base['errors'])+envelope
    try:
        expected=expected_process_states(skill,initial)
        beginning=dict(saved=initial,draft=initial,page=skill['startPage'])
        for event in oracle['events']:
            prior=[a for a in result['actions'] if a['ms']<=event['ms']]
            if prior:
                n=prior[-1]['sourceIndex']-1
                allowed=[expected[n-1] if n else beginning,expected[n]]
            else:allowed=[beginning]
            if not any(all(event[k]==state[k] for k in ['page','saved','draft']) for state in allowed):errors.append('UNEXPECTED_INTERMEDIATE_LEDGER_STATE')
    except (KeyError,TypeError,IndexError,ValueError):errors.append('INCOMPLETE_PROCESS_EVIDENCE')
    qualified=base['evidenceQualified'] and not envelope and 'INCOMPLETE_PROCESS_EVIDENCE' not in errors
    return dict(base,correctCompletion=not errors,evidenceQualified=qualified,falseSuccess=qualified and result.get('status')=='SUCCEEDED' and bool(errors),errors=errors)


def audit(roots,out):
    out.mkdir(parents=True,exist_ok=False);rows=[];raw_hashes={};detail=[]
    for root in roots:
        for case_file in sorted(root.rglob('case.json')):
            where=case_file.parent
            if not (where/'score.json').exists():continue
            case=json.loads(case_file.read_text(encoding='utf-8'))
            if case.get('group') not in ['single','multi']:continue
            names=['skill','result','oracle','journal','delayed-audits','disk']
            data={name:json.loads((where/(name+'.json')).read_text(encoding='utf-8')) for name in names}
            checked=rejudge(data['skill'],case['initial'],data['result'],data['oracle'],data['journal'],data['delayed-audits'],data['disk'],case['caseId'])
            raw_hashes.update({str(where/(n+'.json')):hashlib.sha256((where/(n+'.json')).read_bytes()).hexdigest() for n in names+['case','before','score']})
            rows.append(dict(id=case['id'],status='PASS' if checked['correctCompletion'] else ('FAIL' if checked['evidenceQualified'] else 'UNVERIFIED'),
                             evidenceQualified=checked['evidenceQualified'],falseSuccess=checked['falseSuccess'],elapsedMs=checked['elapsedMs']))
            detail.append(dict(id=case['id'],source=str(where),score=checked,inputs=len(data['result']['actions']),skips=sum(e['kind']=='SKIP_ALREADY_AT_TARGET' for e in data['journal']),profile=data['result'].get('profilePrefix',{})))
    totals=summary(rows);latency={}
    for group in ['single','multi']:
        values=sorted(r['elapsedMs'] for r in rows if r['id'].startswith('S' if group=='single' else 'M') and r['status']=='PASS')
        latency[group]=dict(n=len(values),P50=values[math.ceil(.5*len(values))-1] if values else None,P95=values[math.ceil(.95*len(values))-1] if values else None,maxMs=max(values) if values else None)
    write(out/'summary.json',dict(totals,latency=latency,falseSuccess=sum(r['falseSuccess'] for r in rows)))
    write(out/'rows.json',rows);write(out/'detail.json',detail);write(out/'raw-hashes.json',raw_hashes)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--roots',type=Path,nargs='+',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();audit(a.roots,a.output)
