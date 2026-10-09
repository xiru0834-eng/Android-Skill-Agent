"""Frozen-case acceptance summary; failures remain in the denominator."""
import json
from pathlib import Path

def main():
    root=Path('evaluation/recorder-repair');folder=root/'confirmation'
    rows=json.loads((folder/'results.json').read_text())
    audits=json.loads((folder/'audit-report.json').read_text())
    assert len(rows)==14 and len(audits)==14, 'Incomplete confirmation batch'
    expected_errors={'drop_save':'OBSERVATION_TIMEOUT:NO_CONFIRMED_CHANGE','single_edit':'SINGLE_PAGE_EDIT_NOT_SUPPORTED'}
    report=[]
    for row in rows:
        if 'harnessError' in row:ok=False
        elif row['case'] in expected_errors:
            ok=row['end']=='REJECTED' and row['error']==expected_errors[row['case']] and not row['compiled']
        else:ok=row['end']=='STOPPED' and row['error']=='' and row['steps']==8 and row['compiled']
        report.append(dict(case=row['case'],repeat=row['repeat'],expectedBehavior=ok))
    data=dict(trials=len(rows),expectedBehaviorPasses=sum(r['expectedBehavior'] for r in report),
              completeRecordings=sum(r.get('compiled',False) for r in rows),
              auditPasses=sum(a['status']=='PASS' for a in audits),rows=report,
              provenance='AUTOMATED; not a human acceptance test',
              limits='Single phone, fixed 8-step compiler, no GPT call or skill approval/execution in this batch')
    (root/'confirmation-summary.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in data.items() if k!='rows'},indent=2))
    assert data['expectedBehaviorPasses']==14 and data['auditPasses']==14, 'Acceptance gate failed'

if __name__=='__main__':main()
