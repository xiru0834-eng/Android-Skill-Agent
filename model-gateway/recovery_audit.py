"""Re-score copied evidence without device access or original absolute paths."""
import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path
from recovery_evidence import diagnose,digest
from migration_audit import check_schedule
from startup_audit import input_safety
from workflow_experiment import write


def audit(root):
    root=Path(root).resolve()
    subprocess.run([sys.executable,str(Path(__file__).with_name('migration_audit.py')),str(root)],check=True)
    load=lambda name:json.loads((root/name).read_text(encoding='utf-8'))
    protocol=load('protocol.json');rows=load('results.json');skill=load('skill.json')
    check_schedule(rows,protocol['blocks'])
    if digest(root/'skill.json')!=protocol['skillSha256']:raise ValueError('SKILL_FILE_CHANGED')
    if 'sourceExportSha256' in protocol:
        if digest(root/'source-export.json')!=protocol['sourceExportSha256'] or load('source-export.json')!=skill:
            raise ValueError('ORIGINAL_EXPORT_CHANGED')
    for artifact in protocol['artifacts'].values():
        # Artifact filenames in this protocol are basenames, never external paths.
        if Path(artifact['path']).name!=artifact['path']:raise ValueError('ARTIFACT_PATH')
        if digest(root/artifact['path'])!=artifact['sha256']:raise ValueError('ARTIFACT_CHANGED')
    expected=[(i,b) for i,b in enumerate(protocol['blocks']) for _ in b['cases']]
    safety={k:0 for k in ('afterDeadlineInputs','unexpectedIds','extraInputs')};groups={};diagnoses=[]
    for index,row in enumerate(rows):
        bi,block=expected[index]
        if row['policy']!=block['policy']:raise ValueError('POLICY_SCHEDULE')
        if not row.get('evidence_complete'):continue
        installed=load(f'block-{bi:02d}.json')
        if installed['installedSha256']!=protocol['artifacts'][row['policy']]['sha256']:raise ValueError('WRONG_CONTROLLER')
        if installed['fixtureSha256']!=protocol['artifacts']['fixture']['sha256']:raise ValueError('WRONG_FIXTURE')
        result=load(f'run-{index:03d}/terminal.json');journal=load(f'run-{index:03d}/journal.json')
        if result['recoveryPolicy']!=row['policy'] or result['deadlineMs']-result['startedMs']!=30000:raise ValueError('POLICY_BUDGET')
        diagnosis=diagnose(result,journal)
        if diagnosis!=load(f'run-{index:03d}/diagnosis.json'):raise ValueError('DIAGNOSIS_CHANGED')
        diagnostics=dict(index=index,**diagnosis);diagnoses.append(diagnostics)
        for key,value in input_safety(load(f'run-{index:03d}/oracle.json'),result,skill).items():safety[key]+=value
        waits=[j for j in journal if j['kind']=='RECOVERY_WAIT']
        if row['policy']=='OFF' and waits:raise ValueError('BASELINE_RECOVERY')
        if len(waits)!=result['recoveryReads']:raise ValueError('RECOVERY_COUNT')
        deadlines={}
        for event in waits:
            data=event['data'];target=data['id'];until=data['untilMs']
            if event['phase']!=1 or until>result['deadlineMs']-3500:raise ValueError('RECOVERY_ALLOWANCE')
            if target in deadlines and deadlines[target]!=until:raise ValueError('SLIDING_RECOVERY_CLOCK')
            deadlines[target]=until
        key=row['config']+'/'+row['policy']+'/'+row['case']['condition'];groups.setdefault(key,[]).append(row)
    def group(values):
        times=sorted(v['elapsed_ms'] for v in values)
        return dict(n=len(values),completed=sum(v['confirmed_success'] for v in values),falseSuccess=sum(v['false_success'] for v in values),
                    p50ms=statistics.median(times),minMs=min(times),maxMs=max(times))
    report=dict(oracleAudit=load('reaudit.json')['summary'],inputSafety=safety,groups={k:group(v) for k,v in groups.items()},diagnoses=diagnoses)
    write(root/'recovery-audit.json',report)
    print(json.dumps(dict(oracleAudit=report['oracleAudit'],inputSafety=safety)))
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();audit(a.directory)
