"""Bounded recovery / portability experiments with automatic artifact restoration."""
import argparse
import ast
import json
import random
import shutil
import subprocess
import time
from pathlib import Path
from migration_matrix import CONFIGS, display, effective_display_value, summarize
from recovery_evidence import diagnose, digest, audit_route
from profile_audit import check_profile
from startup_audit import input_safety
from transfer_cases import INITIALS
from transfer_run import approved, run
from transfer_requests import dispatched_requests
from workflow_capture import APP, PROBE
from workflow_experiment import ROOT, adb, write


def blocks(suite):
    if suite.startswith('profile-'):
        rng=random.Random(28401);out=[]
        for repeat in range(1 if suite=='profile-smoke' else 3):
            indices=[0,5] if suite in ('profile-smoke','profile-display') else range(6)
            cases=[dict(initial=list(INITIALS[i]),initialId='S'+str(i),condition='S'+str(i),fault='normal',repeat=repeat) for i in indices]
            faults=['transient_save'] if suite=='profile-smoke' else [] if suite=='profile-display' else ['missing','duplicate','rollback','dirty','drop','late_save','transient_save']
            cases += [dict(initial=list(INITIALS[0]),initialId='S0',condition=f,fault=f,repeat=repeat) for f in faults]
            if suite not in ('profile-smoke','profile-phone','profile-display'):raise ValueError('UNKNOWN_SUITE')
            if suite!='profile-smoke':rng.shuffle(cases)
            configs=['reference','compact'] if suite=='profile-display' else ['phone']
            if suite=='profile-display':rng.shuffle(configs)
            for config in configs:out.append(dict(config=config,policy='R2',repeat=repeat,cases=cases))
        return out
    rng=random.Random(28130);out=[]
    if suite=='r2-development':
        cases=[dict(initial=list(INITIALS[0]),initialId='S0',condition='transient_save',fault='transient_save',repeat=i) for i in range(10)]
        cases += [dict(initial=list(INITIALS[i]),initialId='S'+str(i),condition='S'+str(i),fault='normal',repeat=0) for i in (0,5)]
        cases += [dict(initial=list(INITIALS[0]),initialId='S0',condition=f,fault=f,repeat=0) for f in ('missing','duplicate','rollback')]
        rng.shuffle(cases);return [dict(config='phone',policy='R2',repeat=0,cases=cases)]
    if suite=='display-r2':return [dict(b,policy='R2') for b in blocks('display')]
    if suite not in ('smoke','confirmation','display'):raise ValueError('UNKNOWN_SUITE')
    for repeat in range(1 if suite=='smoke' else 3):
        cases=[dict(initial=list(INITIALS[i]),initialId='S'+str(i),condition='S'+str(i),fault='normal',repeat=repeat)
               for i in ([0,5] if suite=='display' else [0,1,5])]
        if suite!='display':
            cases += [dict(initial=list(INITIALS[0]),initialId='S0',condition=f,fault=f,repeat=repeat)
                      for f in ['transient_save','late_save','missing','duplicate','rollback']]
        if suite=='smoke':cases=[c for c in cases if c['condition'] in ('S0','transient_save')]
        rng.shuffle(cases)
        configs=list(CONFIGS) if suite=='display' else ['phone'];rng.shuffle(configs)
        for config in configs:
            for policy in (['R1'] if suite=='display' else ['OFF','R1'] if repeat%2==0 else ['R1','OFF']):
                out.append(dict(config=config,policy=policy,repeat=repeat,cases=cases))
    return out


def source_closure(directory,names):
    pending=list(names);found=set()
    while pending:
        name=pending.pop()
        if name in found:continue
        path=directory/name
        if not path.is_file():raise ValueError('Missing harness source: '+name)
        found.add(name)
        for node in ast.walk(ast.parse(path.read_text(encoding='utf-8-sig'))):
            imports=[node.module] if isinstance(node,ast.ImportFrom) else [n.name for n in node.names] if isinstance(node,ast.Import) else []
            for module in imports:
                if module and (directory/(module.split('.')[0]+'.py')).is_file():pending.append(module.split('.')[0]+'.py')
    return sorted(found)


def installed_hash(serial,package):
    path=adb(serial,'shell','pm','path',package).strip()
    if not path.startswith('package:') or '\n' in path:raise RuntimeError('APK_PATH')
    path=path[len('package:'):]
    return path,adb(serial,'shell','sha256sum',path).split()[0]


def install(serial,path):
    response=adb(serial,'install','-r','-d',str(path),timeout=45)
    if 'Success' not in response:raise RuntimeError('INSTALL_FAILED: '+response)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--suite',choices=['smoke','confirmation','display','r2-development','display-r2','profile-smoke','profile-phone','profile-display'],required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    profiling=args.suite.startswith('profile-')
    is_display=args.suite.startswith('display') or args.suite=='profile-display';serial='emulator-5554' if is_display else 'R5CW134LLBZ'
    if adb(serial,'get-state').strip()!='device':raise RuntimeError('DEVICE_NOT_READY')
    root=args.output.resolve();root.mkdir(parents=True,exist_ok=False)
    original=display(serial);skill=approved(serial)
    if 'Override' in str(original):raise RuntimeError('UNEXPECTED_DISPLAY_OVERRIDE')
    if skill['finalGoals']!=[1,60,1,1]:raise RuntimeError('FROZEN_GOAL_MISMATCH')
    write(root/'skill.json',skill)
    original_export=ROOT/'evaluation/current-package-migration/source-export/migration-source-v14.json'
    if json.loads(original_export.read_text(encoding='utf-8'))!=skill:raise RuntimeError('SOURCE_EXPORT_MISMATCH')
    shutil.copyfile(original_export,root/'source-export.json')
    (root/'harness').mkdir()
    for name in source_closure(Path(__file__).parent,['recovery_matrix.py','recovery_audit.py']+(['profile_report.py'] if profiling else [])):
        shutil.copyfile(Path(__file__).with_name(name),root/'harness'/name)
    for label,folder in [('probe','android-agent-probe'),('fixture','android-transfer-bench')]:
        shutil.copytree(ROOT/folder/'app/src/main',root/('source-'+label))
    for policy in ('off','r1'):
        shutil.copytree(ROOT/'evaluation/recovery-portability'/(policy+'-v2-source'),root/('source-'+policy))
    schedule=blocks(args.suite);artifacts={};backups={};rows=[]
    if any(b['policy']=='R2' for b in schedule):
        candidate_source=ROOT/'evaluation/reliability-profile/r2-project/app/src/main' if profiling else ROOT/'evaluation/recovery-portability/r2-source'
        shutil.copytree(candidate_source,root/'source-r2')
    for policy in sorted({b['policy'] for b in schedule}):
        path=ROOT/'evaluation/reliability-profile/r2-project/build/manual/demo-probe-profile-r2.apk' if profiling else ROOT/'android-agent-probe/build/manual'/('demo-probe-recovery-'+policy.lower()+'.apk')
        shutil.copyfile(path,root/path.name);artifacts[policy]=dict(path=path.name,sha256=digest(path))
    fixture=ROOT/'android-transfer-bench/build/manual/transfer-bench-recovery-fixture.apk'
    shutil.copyfile(fixture,root/fixture.name);artifacts['fixture']=dict(path=fixture.name,sha256=digest(fixture))
    for package,name in [(PROBE,'original-probe.apk'),(APP,'original-fixture.apk')]:
        path,sha=installed_hash(serial,package);adb(serial,'pull',path,str(root/name))
        if digest(root/name)!=sha:raise RuntimeError('BACKUP_MISMATCH')
        backups[package]=dict(path=name,sha256=sha)
    write(root/'protocol.json',dict(device=serial,suite=args.suite,blocks=schedule,artifacts=artifacts,backups=backups,
        original=original,seed=28401 if profiling else 28130,budgetMs=30000,modelCalls=0,humanDemonstration=False,instrumentation='PREFIX_COUNTERS_V1' if profiling else 'NONE',
        recoveryWaitMs=1500,reserveMs=3500,skillSha256=digest(root/'skill.json'),sourceExportSha256=digest(root/'source-export.json'),
        actualDemonstrator='AUTOMATED_UI_TEST; original HUMAN_DECLARED field preserved, not treated as human evidence',
        expected={'S0':{'OFF':'SUCCEEDED','R1':'SUCCEEDED','R2':'SUCCEEDED'},'S1':{'OFF':'SUCCEEDED','R1':'SUCCEEDED','R2':'SUCCEEDED'},
                  'S5':{'OFF':'SUCCEEDED','R1':'SUCCEEDED','R2':'SUCCEEDED'},'transient_save':{'OFF':'UNCONFIRMED','R1':'SUCCEEDED','R2':'SUCCEEDED'},
                  **{f:{p:'UNCONFIRMED' for p in ('OFF','R1','R2')} for f in ['late_save','missing','duplicate','rollback','dirty','drop']},
                  **{'S'+str(i):{p:'SUCCEEDED' for p in ('OFF','R1','R2')} for i in (2,3,4)}},
        scope='One already reviewed 8-step same-App skill. Injected faults; not cross-App binding.',
        deviceInfo={k:adb(serial,'shell','getprop',v).strip() for k,v in
            [('model','ro.product.model'),('android','ro.build.version.release'),('build','ro.build.fingerprint')]}))
    try:
        install(serial,root/fixture.name)
        if installed_hash(serial,APP)[1]!=artifacts['fixture']['sha256']:raise RuntimeError('FIXTURE_MISMATCH')
        for bi,block in enumerate(schedule):
            policy=block['policy'];config=block['config']
            adb(serial,'shell','am','force-stop',APP)
            if is_display:
                size,density=CONFIGS[config];adb(serial,'shell','wm','size',size);adb(serial,'shell','wm','density',density);time.sleep(3)
            actual=display(serial)
            if is_display and (effective_display_value(actual['size']),effective_display_value(actual['density']))!=CONFIGS[config]:
                raise RuntimeError('DISPLAY_MISMATCH')
            install(serial,root/artifacts[policy]['path'])
            if installed_hash(serial,PROBE)[1]!=artifacts[policy]['sha256']:raise RuntimeError('CONTROLLER_MISMATCH')
            launch=adb(serial,'shell','am','start','-W','-n',PROBE+'/.MainActivity','-f','0x04000000')
            if 'Status: ok' not in launch:raise RuntimeError('OPERATOR_NOT_READY')
            time.sleep(2)
            write(root/f'block-{bi:02d}.json',dict(config=config,policy=policy,display=actual,
                installedSha256=installed_hash(serial,PROBE)[1],fixtureSha256=installed_hash(serial,APP)[1],launch=launch))
            if approved(serial)!=skill:raise RuntimeError('APPROVAL_CHANGED')
            for case in block['cases']:
                directory=root/f'run-{len(rows):03d}'
                try:
                    value=run(serial,case,directory,skill)
                    result=json.loads((directory/'terminal.json').read_text(encoding='utf-8'))
                    if result.get('recoveryPolicy')!=policy:raise RuntimeError('POLICY_MISMATCH')
                    journal=json.loads((directory/'journal.json').read_text(encoding='utf-8'))
                    write(directory/'diagnosis.json',diagnose(result,journal))
                    if profiling:
                        write(directory/'profile-check.json',check_profile(result,journal))
                except Exception as error:
                    directory.mkdir(exist_ok=True)
                    value=dict(case=case,evidence_complete=False,infrastructureFailure=str(error))
                    write(directory/'failure.json',value);rows.append(dict(config=config,policy=policy,**value))
                    write(root/'results.json',rows);raise
                rows.append(dict(config=config,policy=policy,**value));write(root/'results.json',rows)
                if profiling:
                    oracle=json.loads((directory/'oracle.json').read_text(encoding='utf-8'))
                    safety=input_safety(oracle,result,skill);route=audit_route(result,skill)
                    actual=[e['kind'].split(':',1)[1] for e in oracle['events'] if e['ms']>=result['startedMs'] and e['kind'].startswith(('input:','edit:'))]
                    ledger=dispatched_requests(journal,result['actions'])==actual
                    write(directory/'safety-check.json',dict(inputSafety=safety,route=route,inputLedgerMatch=ledger))
                    if not ledger:raise RuntimeError('INPUT_LEDGER_MISMATCH')
                    if value['false_success'] or value['post_terminal_inputs'] or value['non_target_violation'] or any(safety.values()) or not route['valid']:
                        raise RuntimeError('SAFETY_ACCEPTANCE_FAILED')
                    if case['condition'] in ('S5','dirty') and value['inputs']!=0:
                        raise RuntimeError('ZERO_INPUT_ACCEPTANCE_FAILED')
                write(root/'summary.json',summarize(rows,sum(len(b['cases']) for b in schedule)))
                print(f"{len(rows)} {config} {policy} {case['condition']} {value['status']} {value['reason']} {value['elapsed_ms']}ms",flush=True)
    except Exception as error:
        write(root/'aborted.json',dict(error=str(error),attempted=len(rows)));raise
    finally:
        write(root/'results.json',rows);write(root/'summary.json',summarize(rows,sum(len(b['cases']) for b in schedule)))
        restoration={}
        for package,backup in backups.items():
            try:
                install(serial,root/backup['path'])
                restoration[package]=installed_hash(serial,package)[1]==backup['sha256']
            except Exception as error:restoration[package]=dict(error=str(error))
        if is_display:
            adb(serial,'shell','wm','size','reset');adb(serial,'shell','wm','density','reset')
        restoration['display']=display(serial)==original;restoration['approval']=approved(serial)==skill
        write(root/'restored.json',restoration)
        if not all(v is True for v in restoration.values()):raise RuntimeError('RESTORATION_INCOMPLETE')


if __name__=='__main__':main()
