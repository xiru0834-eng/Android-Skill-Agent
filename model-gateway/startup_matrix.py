"""Paired startup-policy study. Normal user execution, unchanged reviewed skill."""
import argparse
import hashlib
import json
import random
import shutil
import subprocess
import time
from pathlib import Path

from migration_matrix import CONFIGS, display, effective_display_value, summarize
from transfer_cases import INITIALS, make_cases
from transfer_run import approved, run
from workflow_capture import APP, PROBE
from workflow_experiment import ADB, ROOT, adb, write


def make_blocks(smoke=False):
    rng=random.Random(28120); blocks=[]
    for repeat in range(1 if smoke else 2):
        configs=['compact'] if smoke else ['reference','compact','wide']
        rng.shuffle(configs)
        for config in configs:
            cases=[dict(initial=list(v),initialId='S'+str(i),condition='S'+str(i),fault='normal',repeat=repeat)
                   for i,v in enumerate(INITIALS[:1] if smoke else INITIALS)]
            rng.shuffle(cases)
            for policy in (['B0','C1'] if repeat==0 else ['C1','B0']):
                blocks.append(dict(config=config,repeat=repeat,policy=policy,cases=cases))
    return blocks


def make_phone_blocks(challenge=False):
    if challenge:
        cases=make_cases('challenge',1)
        return [dict(config='phone-challenge',repeat=0,policy=p,cases=cases) for p in ('B0','C1')]
    rng=random.Random(28121);blocks=[]
    for repeat in range(2):
        cases=[dict(initial=list(v),initialId='S'+str(i),condition='S'+str(i),fault='normal',repeat=repeat)
               for i,v in enumerate(INITIALS)]
        rng.shuffle(cases)
        for policy in (['B0','C1'] if repeat==0 else ['C1','B0']):
            blocks.append(dict(config='phone',repeat=repeat,policy=policy,cases=cases))
    return blocks


def make_failfast_blocks():
    return [dict(config='phone' if suite=='normal' else 'phone-challenge', repeat=0,policy='C2',cases=make_cases(suite,1))
            for suite in ('normal','challenge')]


def summarize_policies(rows,blocks):
    result={'overall':summarize(rows,sum(len(b['cases']) for b in blocks))}
    for policy in sorted({b['policy'] for b in blocks}):
        result[policy]=summarize([r for r in rows if r['policy']==policy],
            sum(len(b['cases']) for b in blocks if b['policy']==policy))
    return result


def validate_policy(result,policy):
    if result.get('startupPolicy')!=policy or result['deadlineMs']-result['startedMs']!=30000:
        raise ValueError('POLICY_OR_BUDGET_MISMATCH')


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path)
    mode=p.add_mutually_exclusive_group();mode.add_argument('--smoke',action='store_true');mode.add_argument('--phone',action='store_true')
    mode.add_argument('--phone-challenge',action='store_true')
    mode.add_argument('--phone-failfast',action='store_true')
    a=p.parse_args();phone=a.phone or a.phone_challenge or a.phone_failfast
    a.output.mkdir(parents=True,exist_ok=False);serial='R5CW134LLBZ' if phone else 'emulator-5554'
    original=display(serial)
    if 'Override' in str(original):raise RuntimeError('Unexpected initial display override')
    skill=approved(serial)
    if skill['finalGoals']!=[1,60,1,1]:raise RuntimeError('Frozen goal mismatch')
    write(a.output/'skill.json',skill)
    blocks=make_failfast_blocks() if a.phone_failfast else make_phone_blocks(a.phone_challenge) if phone else make_blocks(a.smoke);rows=[];artifacts={}
    for policy in sorted({b['policy'] for b in blocks}):
        source=ROOT/'android-agent-probe/build/manual'/('demo-probe-startup-'+policy.lower()+'.apk')
        dest=a.output/source.name;shutil.copyfile(source,dest)
        artifacts[policy]=dict(path=str(dest.resolve()),sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
    sources=a.output/'harness';sources.mkdir()
    for name in ('startup_matrix.py','migration_matrix.py','transfer_run.py','transfer_audit.py','transfer_requests.py',
                 'workflow_score.py','workflow_capture.py','transfer_input_ready.py','transfer_terminal_wait.py','workflow_experiment.py'):
        shutil.copyfile(Path(__file__).with_name(name),sources/name)
    write(a.output/'protocol.json',dict(blocks=blocks,original=original,artifacts=artifacts,modelCalls=0,budgetMs=30000,
        seed=91284 if a.phone_challenge or a.phone_failfast else 28121 if phone else 28120,
        smoke=a.smoke,device=serial,challenge=a.phone_challenge,developmentAblation=a.phone_failfast,
        renderer='physical' if phone else 'host',cores=None if phone else 4,memoryMB=None if phone else 4096,
        scope='Same approved 8-step workflow. Not human recording or cross-app workflow transfer.'))
    try:
        for bi,block in enumerate(blocks):
            policy=block['policy'];label=block['config']
            adb(serial,'shell','am','force-stop',APP)
            if not phone:
                size,density=CONFIGS[label]
                adb(serial,'shell','wm','size',size);adb(serial,'shell','wm','density',density);time.sleep(3)
            actual=display(serial)
            if not phone and (effective_display_value(actual['size'])!=size or effective_display_value(actual['density'])!=density):
                raise RuntimeError('Display mismatch')
            installation=adb(serial,'install','-r',artifacts[policy]['path'],timeout=40)
            if 'Success' not in installation:raise RuntimeError('Install failed: '+installation)
            path=adb(serial,'shell','pm','path',PROBE).strip()
            if not path.startswith('package:') or '\n' in path:raise RuntimeError('Unexpected APK paths')
            installed=adb(serial,'shell','sha256sum',path[len('package:'):]).split()[0]
            if installed!=artifacts[policy]['sha256']:raise RuntimeError('Installed artifact mismatch')
            # Warm only the operator; the tested target launch remains inside the task budget.
            launch=adb(serial,'shell','am','start','-W','-n',PROBE+'/.MainActivity','-f','0x04000000')
            if 'Status: ok' not in launch:raise RuntimeError('Operator launch failed')
            time.sleep(3)
            write(a.output/f'block-{bi:02d}.json',dict(config=label,policy=policy,display=actual,
                installedSha256=installed,launch=launch,services=adb(serial,'shell','settings','get','secure','enabled_accessibility_services')))
            if approved(serial)!=skill:raise RuntimeError('Approved skill changed during installation')
            for case in block['cases']:
                directory=a.output/f'run-{len(rows):03d}'
                try:
                    score=run(serial,case,directory,skill)
                    terminal=json.loads((directory/'terminal.json').read_text(encoding='utf-8'))
                    validate_policy(terminal,policy)
                except Exception as error:
                    directory.mkdir(exist_ok=True)
                    score=dict(case=case,evidence_complete=False,infrastructureFailure=str(error))
                    write(directory/'failure.json',score)
                    rows.append(dict(config=label,policy=policy,**score));write(a.output/'results.json',rows)
                    raise
                rows.append(dict(config=label,policy=policy,**score));write(a.output/'results.json',rows)
                write(a.output/'summary.json',summarize_policies(rows,blocks))
                print(f"{len(rows)} {label} {policy} {case['initialId']} {score['status']} {score['reason']} {score['elapsed_ms']}ms",flush=True)
            shot=subprocess.run([str(ADB),'-s',serial,'exec-out','screencap','-p'],capture_output=True,check=True,timeout=20)
            (a.output/f'block-{bi:02d}.png').write_bytes(shot.stdout)
    except Exception as error:
        write(a.output/'aborted.json',dict(error=str(error),completed=len(rows)));raise
    finally:
        write(a.output/'summary.json',summarize_policies(rows,blocks))
        try:
            if not phone:
                adb(serial,'shell','wm','size','reset');adb(serial,'shell','wm','density','reset')
            restored=display(serial)
            write(a.output/'restored.json',dict(actual=restored,matches=restored==original))
            if restored!=original:raise RuntimeError('Display restoration mismatch')
        except Exception as error:
            write(a.output/'restore-error.json',dict(error=str(error)))
            raise


if __name__=='__main__':main()
