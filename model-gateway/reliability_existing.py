"""Regression of the installed reviewed workflow, without installation or approval writes."""
import argparse
import json
import shutil
from pathlib import Path
from migration_matrix import display,summarize
from recovery_matrix import installed_hash,source_closure
from recovery_evidence import digest,diagnose,audit_route
from startup_audit import input_safety
from transfer_cases import make_cases
from transfer_requests import dispatched_requests
from transfer_run import approved,run
from workflow_capture import APP,PROBE
from workflow_experiment import adb,write


def schedule(suite):
    return [dict(config='phone',policy='INSTALLED',cases=make_cases(suite,3))]


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--suite',choices=['normal','challenge'],default='normal')
    args=parser.parse_args();serial='R5CW134LLBZ'
    if adb(serial,'get-state').strip()!='device':raise RuntimeError('DEVICE_NOT_READY')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    skill=approved(serial);original=display(serial);hashes={};artifacts={}
    if skill['appPackage']!=APP or skill['finalGoals']!=[1,60,1,1]:raise RuntimeError('SKILL_MISMATCH')
    write(root/'skill.json',skill)
    for package,name in ((APP,'installed-fixture.apk'),(PROBE,'installed-probe.apk')):
        path,sha=installed_hash(serial,package);adb(serial,'pull',path,str(root/name))
        if digest(root/name)!=sha:raise RuntimeError('BACKUP_MISMATCH')
        hashes[package]=sha;artifacts[package]=dict(path=name,sha256=sha)
    blocks=schedule(args.suite);planned=sum(len(b['cases']) for b in blocks)
    (root/'harness').mkdir()
    for name in source_closure(Path(__file__).parent,['reliability_existing.py','migration_audit.py']):
        shutil.copyfile(Path(__file__).with_name(name),root/'harness'/name)
    write(root/'protocol.json',dict(device=serial,blocks=blocks,original=original,artifacts=artifacts,suite=args.suite,
        skillSha256=digest(root/'skill.json'),budgetMs=30000,seed=91284,modelCalls=0,humanDemonstration=False,
        installationPerformed=False,scope='Existing installed version; one previously approved 8-step skill, repeated initial states. No candidate performance inference.'))
    rows=[]
    try:
        for case in blocks[0]['cases']:
            if display(serial)!=original or any(installed_hash(serial,p)[1]!=h for p,h in hashes.items()):raise RuntimeError('ENVIRONMENT_CHANGED')
            directory=root/f'run-{len(rows):03d}'
            try:
                value=run(serial,case,directory,skill)
            except Exception as error:
                directory.mkdir(exist_ok=True);write(directory/'failure.json',dict(error=str(error)))
                rows.append(dict(config='phone',policy='INSTALLED',case=case,evidence_complete=False,infrastructureFailure=str(error)));raise
            rows.append(dict(config='phone',policy='INSTALLED',**value));write(root/'results.json',rows)
            load=lambda name:json.loads((directory/name).read_text(encoding='utf-8'))
            result,journal,oracle=load('terminal.json'),load('journal.json'),load('oracle.json')
            route=audit_route(result,skill);safety=input_safety(oracle,result,skill)
            actual=[e['kind'].split(':',1)[1] for e in oracle['events'] if e['ms']>=result['startedMs'] and e['kind'].startswith(('input:','edit:'))]
            ledger=dispatched_requests(journal,result['actions'])==actual
            write(directory/'safety-check.json',dict(route=route,inputSafety=safety,inputLedgerMatch=ledger))
            write(directory/'diagnosis.json',diagnose(result,journal))
            if not ledger or not route['valid'] or any(safety.values()) or value['false_success'] or value['post_terminal_inputs'] or value['non_target_violation']:
                raise RuntimeError('SAFETY_ACCEPTANCE_FAILED')
            if (case['initialId']=='S5' or case['fault']=='dirty') and value['inputs']!=0:raise RuntimeError('ZERO_INPUT_ACCEPTANCE_FAILED')
            if result['deadlineMs']-result['startedMs']!=30000:raise RuntimeError('TASK_BUDGET_CHANGED')
            print(f"{len(rows)}/{planned} {case['condition']} {value['status']} {value['reason']} {value['elapsed_ms']}ms inputs={value['inputs']}",flush=True)
    except Exception as error:
        write(root/'aborted.json',dict(error=str(error),attempted=len(rows)));raise
    finally:
        write(root/'results.json',rows);write(root/'summary.json',summarize(rows,planned))
        unchanged={p:installed_hash(serial,p)[1]==h for p,h in hashes.items()}
        unchanged.update(approval=approved(serial)==skill,display=display(serial)==original)
        write(root/'unchanged.json',unchanged)
        if not all(unchanged.values()):raise RuntimeError('ENVIRONMENT_CHANGED')


if __name__=='__main__':main()
