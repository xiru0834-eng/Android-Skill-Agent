"""Strict evidence envelope around the existing independent state adjudicator."""
from workflow_score import score

def evaluate(oracle,result,goal,audits,*,case_id,run_id):
    if result.get('runId')!=run_id or oracle.get('caseId')!=case_id:
        raise ValueError('RUN_CORRELATION')
    if len(audits)!=3 or audits[0]['capturedMs']<result['finishedMs'] or audits[-1]['capturedMs']-result['finishedMs']<5000:
        raise ValueError('AUDIT_WINDOW_INCOMPLETE')
    previous=result['finishedMs']
    for sample in audits:
        data=sample['oracle'];when=sample['capturedMs']
        if when<previous or data.get('caseId')!=case_id or data.get('initial')!=oracle['initial']:
            raise ValueError('AUDIT_CORRELATION')
        if data['events']!=oracle['events'][:len(data['events'])]:raise ValueError('LEDGER_REWRITTEN')
        previous=when
    if audits[-1]['oracle']!=oracle:raise ValueError('FINAL_AUDIT_MISMATCH')
    value=score(oracle,result,goal)
    value['evidence_complete']=True
    value['non_target_applicability']='N/A' if all(v is not None for v in goal) else 'MEASURED'
    return value
