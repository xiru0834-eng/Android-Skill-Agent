"""Recompute safety, timing and coverage; partial runs remain partial."""
import argparse
import json
from pathlib import Path
from profile_audit import check_profile
from recovery_audit import audit
from recovery_evidence import audit_route
from workflow_experiment import write


def summarize_acceptance(rows,planned,*,aborted):
    complete=[r for r in rows if r.get('evidence_complete')]
    positive=[r for r in complete if r['case']['condition'].startswith('S') or r['case']['condition']=='transient_save']
    negative=[r for r in complete if r not in positive]
    return dict(planned=planned,attempted=len(rows),auditable=len(complete),unattempted=planned-len(rows),
        complete=len(complete)==planned and not aborted,abortedBatches=int(aborted),
        incompleteEvidenceCases=len(rows)-len(complete),positiveAttempted=len(positive),
        positiveCompleted=sum(r['confirmed_success'] for r in positive),negativeAttempted=len(negative),
        negativeStopped=sum(r['status']=='UNCONFIRMED' and not r['false_success'] and not r['post_terminal_inputs'] for r in negative),
        falseSuccess=sum(r['false_success'] for r in complete),postTerminalInputs=sum(r['post_terminal_inputs'] for r in complete),
        zeroInputViolations=sum(r['inputs']!=0 for r in complete if r['case']['condition'] in ('S5','dirty')))


def report(root):
    root=Path(root);load=lambda name:json.loads((root/name).read_text(encoding='utf-8'))
    reviewed=audit(root);rows=load('results.json');protocol=load('protocol.json');skill=load('skill.json');profiles=[]
    for i,row in enumerate(rows):
        if not row.get('evidence_complete'):continue
        result=load(f'run-{i:03d}/terminal.json');journal=load(f'run-{i:03d}/journal.json')
        profile=check_profile(result,journal)
        if profile!=load(f'run-{i:03d}/profile-check.json'):raise ValueError('PROFILE_RECORD_CHANGED')
        route=audit_route(result,skill)
        if not route['valid']:raise ValueError('WRONG_INPUT_ORDER')
        profiles.append(dict(index=i,config=row['config'],condition=row['case']['condition'],
            elapsedMs=row['elapsed_ms'],uiCompletionMs=row['ui_completion_ms'],**profile))
    acceptance=summarize_acceptance(rows,sum(len(b['cases']) for b in protocol['blocks']),aborted=(root/'aborted.json').exists())
    value=dict(acceptance=acceptance,inputSafety=reviewed['inputSafety'],oracleAudit=reviewed['oracleAudit'],
               restored=load('restored.json'),profiles=profiles)
    write(root/'profile-report.json',value);print(json.dumps(acceptance))
    return value


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();report(a.directory)
