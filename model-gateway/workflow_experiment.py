"""Scoped device experiments; fixture preparation and adjudication stay outside executor."""
import argparse
import hashlib
import json
import random
import secrets
import shutil
import statistics
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from workflow_score import score

ROOT=Path(__file__).resolve().parents[1]
ADB=Path('D:/python_code/closed-loop-gui-agent/tools/platform-tools/adb.exe')
PKG='edu.sydney.transferlab'

def cases(suite, repeats):
    rows=[]
    if suite=='normal':
        for layout in ('single','multi'):
            for load in (2,4):
                for variant in (0,1):
                    full=[1,60,1,1] if variant==0 else [0,80,0,2]
                    goal=full if load==4 else ([1,None,None,1] if variant==0 else [None,80,0,None])
                    wrong=[1-full[0],40,1-full[2],3]
                    for initial_kind in ('none','partial','all'):
                        initial=wrong.copy()
                        for i,target in enumerate(goal):
                            if target is not None and (initial_kind=='all' or initial_kind=='partial' and i<2):initial[i]=target
                        for repeat in range(repeats):
                            pair=f'{layout}-{load}-{variant}-{initial_kind}-{repeat}'
                            for policy in ('R1','P'):
                                rows.append(dict(pair=pair,layout=layout,load=load,variant=variant,initial_kind=initial_kind,
                                    initial=initial,goal=goal,policy=policy,fault='normal',expect='SUCCEEDED',repeat=repeat))
    elif suite=='challenge':
        for layout in ('single','multi'):
            for fault in ('drop','delay','navdelay','rollback','missing','duplicate','dirty','cancel'):
                for repeat in range(repeats):
                    for policy in ('R1','P'):
                        rows.append(dict(pair=f'{layout}-{fault}-{repeat}',layout=layout,load=4,initial_kind='none',
                            initial=[0,40,0,3],goal=[1,60,1,1],policy=policy,fault=fault,repeat=repeat,
                            expect='SUCCEEDED' if fault in ('delay','navdelay') else 'CANCELLED' if fault=='cancel' else 'UNCONFIRMED'))
    else:raise ValueError('Unknown suite')
    return rows

def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def adb(serial,*args,timeout=40):
    process=subprocess.run([str(ADB),'-s',serial,*map(str,args)],capture_output=True,timeout=timeout)
    out=process.stdout.decode('utf-8',errors='replace')
    if process.returncode:raise RuntimeError('ADB failed: '+process.stderr.decode('utf-8',errors='replace')[:300])
    return out

def private_json(serial,package,file):
    if package not in (PKG,'edu.sydney.evaluation'):raise ValueError('Package not allowed')
    return json.loads(adb(serial,'shell','run-as',package,'cat','files/'+file))

def run(serial,case,directory):
    directory.mkdir();nonce=secrets.token_hex(8)
    write(directory/'case.json',dict(case,runId=nonce))
    fault=case['fault'] if case['fault']!='cancel' else 'normal'
    launch=adb(serial,'shell','am','start','-W','-n',PKG+'/.WorkflowActivity','--es','layout',case['layout'],
        '--es','initial',','.join(map(str,case['initial'])),'--es','fault',fault,'--es','caseId',nonce)
    (directory/'launch.txt').write_text(launch,encoding='utf-8')
    time.sleep(.4)
    before=private_json(serial,PKG,'workflow-oracle.json');write(directory/'before.json',before)
    if before['caseId']!=nonce or before['initial']!=case['initial']:raise RuntimeError('Fixture reset not verified')
    arguments=['shell','am','instrument','-w','-e','policy',case['policy'],'-e','runId',nonce,
        '-e','goal',','.join('-1' if x is None else str(x) for x in case['goal'])]
    if case['fault']=='cancel':arguments+=['-e','cancelAfter','2']
    output=adb(serial,*arguments,'edu.sydney.evaluation/.WorkflowDriver',timeout=35)
    (directory/'instrumentation.txt').write_text(output,encoding='utf-8')
    result=private_json(serial,'edu.sydney.evaluation','workflow-result.json');write(directory/'result.json',result)
    if result['runId']!=nonce:raise RuntimeError('Stale executor result')
    time.sleep(1.1) # Read-only post-terminal stability audit, not extra execution budget.
    oracle=private_json(serial,PKG,'workflow-oracle.json');write(directory/'oracle.json',oracle)
    if oracle['caseId']!=nonce:raise RuntimeError('Fixture changed during run')
    preferences=ET.fromstring(adb(serial,'shell','run-as',PKG,'cat','shared_prefs/WorkflowActivity.xml'))
    persisted=next((e.text for e in preferences if e.attrib.get('name')=='committed'),None)
    persisted=[int(x) for x in persisted.split(',')] if persisted else None
    write(directory/'persisted.json',persisted)
    if persisted!=oracle['events'][-1]['saved']:raise RuntimeError('Persisted state and event ledger disagree')
    judged=score(oracle,result,case['goal'])
    judged['reason']=result['reason']
    judged['expected_behavior']=(judged['confirmed_success'] if case['expect']=='SUCCEEDED' else
        result['status']==case['expect'] and not judged['false_success'] and not judged['non_target_violation'] and judged['post_terminal_inputs']==0)
    expected_reason={'drop':'SAVE_UNCONFIRMED','rollback':'FINAL_TARGET_MISMATCH','missing':'MISSING:wfFanSave',
        'duplicate':'AMBIGUOUS:wfLampPower','dirty':'USER_UNSAVED_EDITS','cancel':'CANCELLED'}.get(case['fault'])
    if expected_reason:judged['expected_behavior'] &= result['reason']==expected_reason
    # Joint-check counterfactual is a trace audit only, not an online ablation run.
    historical={}
    for step in result.get('steps',[]):
        i=step['group']*2
        historical[step['group']]=all(case['goal'][j] is None or step['saved'][j]==case['goal'][j] for j in (i,i+1))
    judged['historical_steps_would_accept']=len(historical)==2 and all(historical.values())
    write(directory/'score.json',judged)
    return dict(case,**judged,run_directory=directory.name)

def summarize(rows):
    groups={}
    for row in rows:
        key=f"{row['layout']}/{row.get('load')}/{row['policy']}/{row.get('initial_kind')}"
        groups.setdefault(key,[]).append(row)
    def agg(values):
        times=sorted(r['elapsed_ms'] for r in values)
        return dict(n=len(values),confirmed=sum(r['confirmed_success'] for r in values),
            actual=sum(r['actual_success'] for r in values),expected=sum(r['expected_behavior'] for r in values),
            false_success=sum(r['false_success'] for r in values),non_target=sum(r['non_target_violation'] for r in values),
            median_ms=statistics.median(times),min_ms=min(times),max_ms=max(times),
            median_inputs=statistics.median(r['inputs'] for r in values))
    return dict(total=agg(rows) if rows else {},groups={k:agg(v) for k,v in groups.items()})

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--device',choices=['emulator-5554','R5CW134LLBZ'],required=True)
    parser.add_argument('--suite',choices=['normal','challenge'],required=True)
    parser.add_argument('--repeats',type=int,choices=[1,2,3],default=2)
    parser.add_argument('--limit',type=int,default=0);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--allow-experiment',action='store_true');args=parser.parse_args()
    if not args.allow_experiment:parser.error('Explicit experiment flag required')
    if args.output.exists():parser.error('Output must be new; prior evidence is never overwritten')
    if adb(args.device,'get-state').strip()!='device':raise RuntimeError('Device not ready')
    args.output.mkdir(parents=True)
    pair_map={}
    for row in cases(args.suite,args.repeats):pair_map.setdefault(row['pair'],[]).append(row)
    rng=random.Random(7831);pairs=list(pair_map.values());rng.shuffle(pairs)
    ordered=[]
    for pair in pairs:rng.shuffle(pair);ordered.extend(pair)
    if args.limit:ordered=ordered[:args.limit]
    sources=[Path(__file__),ROOT/'model-gateway/workflow_score.py',
        ROOT/'android-transfer-bench/app/src/main/java/edu/sydney/transferlab/WorkflowActivity.java',
        ROOT/'android-transfer-bench/app/src/main/java/edu/sydney/transferlab/WorkflowState.java',
        ROOT/'evaluation/android-observer/app/src/main/java/edu/sydney/evaluation/WorkflowDriver.java',
        ROOT/'evaluation/android-observer/app/src/main/java/edu/sydney/evaluation/WorkflowPolicy.java']
    snapshots=args.output/'sources';snapshots.mkdir()
    hashes={}
    for source in sources:shutil.copy2(source,snapshots/source.name);hashes[str(source.relative_to(ROOT))]=hashlib.sha256(source.read_bytes()).hexdigest()
    apk_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (
        ROOT/'android-transfer-bench/build/manual/transfer-bench-workflow-dev.apk',
        ROOT/'evaluation/android-observer/build/manual/observer-workflow-dev.apk')}
    write(args.output/'protocol.json',dict(stage='development',device=args.device,suite=args.suite,seed=7831,
        deadline_ms=20000,step_wait_ms=3000,audit_ms=1100,source_hashes=hashes,apk_hashes=apk_hashes,cases=ordered,
        limitations=['R0 and production skill integration not implemented','No GPT calls','Synthetic app; no third-party generalization']))
    results=[]
    for i,case in enumerate(ordered):
        directory=args.output/f'{i:03d}-{case["policy"]}'
        try:row=run(args.device,case,directory)
        except Exception as error:
            write(args.output/'blocked.json',dict(index=i,case=case,error=str(error)));raise
        results.append(row);write(args.output/'results.json',results);write(args.output/'summary.json',summarize(results))
        print(f'{i+1}/{len(ordered)} {case["layout"]} {case["policy"]} {case["fault"]} {row["status"]} '
              f'actual={row["actual_success"]} expected={row["expected_behavior"]} ms={row["elapsed_ms"]}',flush=True)
    print(json.dumps(summarize(results)['total']),flush=True)

if __name__=='__main__':main()
