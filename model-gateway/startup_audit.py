"""Independent policy/budget/pair checks on top of the oracle replay audit."""
import argparse
import hashlib
import json
import statistics
import subprocess
import sys
from pathlib import Path
from startup_matrix import validate_policy
from workflow_experiment import write


def input_safety(oracle,result,skill):
    events=[e for e in oracle['events'] if e['ms']>=result['startedMs'] and e['kind'].startswith(('input:','edit:'))]
    allowed={s['id'] for s in skill['steps']}
    changes=sum(a!=b for a,b in zip(oracle['initial'],skill['finalGoals']))
    expected=4+changes if changes else 0  # Four navigation/save inputs in this fixed 8-step route.
    return dict(afterDeadlineInputs=sum(e['ms']>=result['deadlineMs'] for e in events),
        unexpectedIds=sum(e['kind'].split(':',1)[1] not in allowed for e in events),
        extraInputs=max(0,len(events)-expected))


def paired(rows):
    groups={}
    for row in rows:
        key=(row['config'],row['case']['repeat'],row['case'].get('condition',row['case']['initialId']))
        group=groups.setdefault(key,{})
        if row['policy'] in group:raise ValueError('Duplicate condition/policy')
        group[row['policy']]=row
    output=dict(pairedTasks=0,unpairedTasks=0,bothSuccess=0,baselineOnlySuccess=0,candidateOnlySuccess=0,bothFail=0)
    deltas={False:[],True:[]}
    for key,group in groups.items():
        if set(group)!= {'B0','C1'} or not all(r.get('evidence_complete') for r in group.values()):
            output['unpairedTasks']+=1;continue
        output['pairedTasks']+=1
        a,b=group['B0'],group['C1'];sa,sb=a['confirmed_success'],b['confirmed_success']
        output['bothSuccess' if sa and sb else 'baselineOnlySuccess' if sa else 'candidateOnlySuccess' if sb else 'bothFail']+=1
        if sa and sb:deltas[key[2]=='S5'].append(b['elapsed_ms']-a['elapsed_ms'])
    output['needsInputDeltaMedianMs']=statistics.median(deltas[False]) if deltas[False] else None
    output['alreadyDeltaMedianMs']=statistics.median(deltas[True]) if deltas[True] else None
    output['latencyMeaning']='C1 minus B0, paired successful tasks only; positive is slower; no independence claim'
    return output


def main():
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);a=p.parse_args();root=a.directory.resolve()
    # Recompute all scores from independent App state and actual input events first.
    subprocess.run([sys.executable,str(Path(__file__).with_name('migration_audit.py')),str(root)],check=True)
    load=lambda name:json.loads((root/name).read_text(encoding='utf-8'))
    rows=load('results.json');protocol=load('protocol.json');skill=load('skill.json');checks=[]
    expected=[(i,b['policy']) for i,b in enumerate(protocol['blocks']) for _ in b['cases']]
    for i,row in enumerate(rows):
        block,policy=expected[i]
        if row['policy']!=policy:raise ValueError('Policy order changed')
        if not row.get('evidence_complete'):continue
        result=load(f'run-{i:03d}/terminal.json');validate_policy(result,policy)
        artifact=protocol['artifacts'][policy]
        if hashlib.sha256(Path(artifact['path']).read_bytes()).hexdigest()!=artifact['sha256']:raise ValueError('APK changed')
        if load(f'block-{block:02d}.json')['installedSha256']!=artifact['sha256']:raise ValueError('Installed APK changed')
        journal=load(f'run-{i:03d}/journal.json')
        checks.append(dict(index=i,policy=policy,startupReadyMs=result.get('startupReadyMs'),
            **input_safety(load(f'run-{i:03d}/oracle.json'),result,skill),
            rootKinds=sorted({j['data']['rootKind'] for j in journal if j['kind']=='ERROR' and 'rootKind' in j['data']})))
    result=dict(oracleAudit=load('reaudit.json')['summary'],pairs=paired(rows),trials=checks,
        inputSafety={k:sum(r[k] for r in checks) for k in ('afterDeadlineInputs','unexpectedIds','extraInputs')})
    write(root/'policy-audit.json',result);print(json.dumps(result['pairs']))


if __name__=='__main__':main()
