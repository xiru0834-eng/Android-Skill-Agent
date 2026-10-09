"""Frozen evaluation of the user's existing skill; does not alter the executor."""
import argparse
import hashlib
import json
import math
import random
import shutil
import statistics
import subprocess
import time
from pathlib import Path
from transfer_run import approved,run
from workflow_capture import APP,PROBE,tree,workbench,click
from workflow_experiment import adb,write,ROOT,ADB
from migration_matrix import display,effective_display_value
from recovery_evidence import audit_route,diagnose
from startup_audit import input_safety

GOAL=[1,100,1,1]
WRONG=[0,40,0,3]
CONFIGS={'reference':('1080x2400','420'),'same-dp':('720x1600','280'),
         'compact':('720x1280','420'),'wide':('1600x2560','320')}
FAIL_REASONS={'drop':'STEP_UNCONFIRMED','rollback':'FINAL_TARGET_MISMATCH','missing':'MISSING:wfFanSave',
              'duplicate':'AMBIGUOUS:wfLampPower','dirty':'INVALID_START'}
SKILL=ROOT/'evaluation/user-recording-100/saved-skill.json'

def phone_cases(suite):
    rng=random.Random(291004);rows=[]
    for repeat in range(2):
        if suite=='normal':
            block=[dict(condition=f'mask-{mask:04b}',initial=[GOAL[i] if mask&(1<<i) else WRONG[i] for i in range(4)],
                fault='normal',expect='SUCCEEDED',repeat=repeat) for mask in range(16)]
        elif suite=='challenge':
            block=[dict(condition=f,initial=WRONG.copy(),fault=f,expect='SUCCEEDED' if f in ('delay','navdelay') else 'UNCONFIRMED',expectedReason=FAIL_REASONS.get(f,'ALL_TARGETS_VERIFIED'),repeat=repeat)
                for f in ('delay','navdelay','drop','rollback','missing','duplicate','dirty')]
        else:raise ValueError('SUITE')
        rng.shuffle(block);rows.extend(block)
    return rows

def display_cases():
    rng=random.Random(291005);rows=[]
    for repeat in range(2):
        configs=list(CONFIGS);rng.shuffle(configs)
        for config in configs:
            block=[dict(condition=name,initial=v.copy(),fault='normal',expect='SUCCEEDED',repeat=repeat,config=config)
                for name,v in [('none',WRONG),('partial',[1,100,0,3]),('all',GOAL)]]
            rng.shuffle(block);rows.extend(block)
    return rows

def expectation(row,case,route_ok,safety):
    clean=not row['false_success'] and route_ok and not safety['unexpectedIds'] and not safety['afterDeadlineInputs']
    if case.get('expectedReason') is not None:clean=clean and row.get('reason')==case['expectedReason']
    return bool(clean and (row['confirmed_success'] if case['expect']=='SUCCEEDED' else row['status']==case['expect']))

def snapshot(serial,out):
    out.mkdir(parents=True,exist_ok=False)
    data=dict(display=display(serial),device=serial,packages={})
    for pkg,label in [(PROBE,'probe'),(APP,'fixture'),('edu.sydney.evaluation','observer')]:
        path=adb(serial,'shell','pm','path',pkg).strip().removeprefix('package:')
        if not path or '\n' in path:raise RuntimeError('APK_PATH')
        sha=adb(serial,'shell','sha256sum',path).split()[0]
        adb(serial,'pull',path,out/(label+'.apk'))
        assert hashlib.sha256((out/(label+'.apk')).read_bytes()).hexdigest()==sha
        data['packages'][pkg]=dict(sha256=sha)
    write(out/'approved.json',approved(serial))
    write(out/'device.json',data)
    print('BACKED UP '+serial,flush=True)

def review_import(serial,out):
    import xml.etree.ElementTree as ET
    out.mkdir(parents=True,exist_ok=False)
    skill=json.loads(SKILL.read_text(encoding='utf-8'))
    prefs=ET.fromstring(adb(serial,'shell','run-as',PROBE,'cat','shared_prefs/recorded_workflows.xml'))
    assert json.loads(next(n.text for n in prefs if n.get('name')=='draft'))==skill
    workbench(serial);click(serial,'flowReview')
    ui=tree(serial);assert any('Review workflow' in n.get('text','') and '审核' in n.get('text','') for n in ui.iter('node'))
    assert any('[1,100,1,1]' in n.get('text','') for n in ui.iter('node'))
    (out/'review.xml').write_bytes(ET.tostring(ui,encoding='utf-8'))
    (out/'review.png').write_bytes(subprocess.check_output([str(ADB),'-s',serial,'exec-out','screencap','-p'],timeout=20))
    click(serial,'button1','android');assert approved(serial)==skill
    write(out/'review.json',dict(saved=True,via='normal UI review',skill=skill))
    print('Reviewed on target device; identical skill saved.')

def summary(rows,planned):
    scored=[r for r in rows if r.get('evidence_complete')]
    def stats(items):
        times=sorted(r['elapsed_ms'] for r in items)
        return dict(n=len(items),actual=sum(r['actual_success'] for r in items),confirmed=sum(r['confirmed_success'] for r in items),
            expected=sum(r['expectedBehavior'] for r in items),falseSuccess=sum(r['false_success'] for r in items),
            unconfirmedSuccess=sum(r['unconfirmed_success'] for r in items),
            zeroInputs=sum(r['inputs']==0 for r in items),p50ms=statistics.median(times) if times else None,
            p95ms=times[math.ceil(.95*len(times))-1] if times else None,maxMs=max(times) if times else None,
            inputSafety={k:sum(r['inputSafety'][k] for r in items) for k in ('unexpectedIds','afterDeadlineInputs','extraInputs')})
    return dict(planned=planned,attempted=len(rows),unrun=planned-len(rows),infrastructureFailures=len(rows)-len(scored),
        scored=stats(scored),groups={k:stats([r for r in scored if r['case'].get('config',r['case']['fault'])==k])
            for k in sorted({r['case'].get('config',r['case']['fault']) for r in scored})})

def restore_display(serial,original):
    for key in ('size','density'):
        value=effective_display_value(original[key]) if 'Override ' in original[key] else 'reset'
        adb(serial,'shell','wm',key,value)
    if display(serial)!=original:raise RuntimeError('DISPLAY_RESTORE')

def execute(serial,suite,out):
    out.mkdir(parents=True,exist_ok=False)
    skill=json.loads(SKILL.read_text(encoding='utf-8'));assert approved(serial)==skill and skill['finalGoals']==GOAL
    cases=display_cases() if suite=='display' else phone_cases(suite)
    if suite=='display' and serial!='emulator-5554':raise ValueError('DISPLAY_ONLY_EMULATOR')
    original=display(serial);write(out/'skill.json',skill)
    write(out/'protocol.json',dict(device=serial,suite=suite,cases=cases,originalDisplay=original,budgetMs=30000,
        modelCalls=0,sourceSkillSha256=hashlib.sha256(SKILL.read_bytes()).hexdigest()))
    sources=out/'harness';sources.mkdir()
    for name in ('user_robustness.py','transfer_run.py','transfer_audit.py','workflow_score.py','workflow_capture.py','startup_audit.py','recovery_evidence.py','transfer_input_ready.py'):
        shutil.copy2(Path(__file__).with_name(name),sources/name)
    rows=[];last_config=None
    try:
        for i,case in enumerate(cases):
            folder=out/f'run-{i:03d}'
            try:
                if suite=='display' and last_config!=case['config']:
                    size,density=CONFIGS[case['config']]
                    adb(serial,'shell','am','force-stop',APP)
                    adb(serial,'shell','wm','size',size);adb(serial,'shell','wm','density',density);time.sleep(3)
                    current=display(serial);write(out/f'display-{i:03d}.json',current)
                    assert effective_display_value(current['size'])==size and effective_display_value(current['density'])==density
                    adb(serial,'shell','am','start','-W','-n',PROBE+'/.MainActivity');time.sleep(2)
                    last_config=case['config']
                row=run(serial,case,folder,skill)
                terminal=json.loads((folder/'terminal.json').read_text(encoding='utf-8'))
                oracle=json.loads((folder/'oracle.json').read_text(encoding='utf-8'))
                journal=json.loads((folder/'journal.json').read_text(encoding='utf-8'))
                route=audit_route(terminal,skill);safety=input_safety(oracle,terminal,skill)
                row.update(route=route,inputSafety=safety,diagnosis=diagnose(terminal,journal),
                    expectedBehavior=expectation(row,case,route['valid'],safety))
                write(folder/'expanded-score.json',row)
                if suite=='display' and (i%3==0 or not row['expectedBehavior']):
                    import xml.etree.ElementTree as ET
                    (folder/'screen.xml').write_bytes(ET.tostring(tree(serial),encoding='utf-8'))
                    (folder/'screen.png').write_bytes(subprocess.check_output([str(ADB),'-s',serial,'exec-out','screencap','-p'],timeout=20))
            except Exception as exc:
                folder.mkdir(exist_ok=True)
                row=dict(case=case,evidence_complete=False,infrastructureFailure=type(exc).__name__+': '+str(exc))
                write(folder/'failure.json',row);rows.append(row);write(out/'results.json',rows)
                raise
            rows.append(row);write(out/'results.json',rows);write(out/'summary.json',summary(rows,len(cases)))
            print(json.dumps(dict(index=i,of=len(cases),condition=case['condition'],config=case.get('config'),
                status=row['status'],reason=row['reason'],expected=row['expectedBehavior'],ms=row['elapsed_ms'])),flush=True)
    finally:
        write(out/'summary.json',summary(rows,len(cases)))
        if suite=='display':restore_display(serial,original)
        write(out/'restoration.json',dict(displayUnchanged=display(serial)==original,skillUnchanged=approved(serial)==skill))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['snapshot','approve','normal','challenge','display']);p.add_argument('--device',required=True,choices=['R5CW134LLBZ','emulator-5554']);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='snapshot':snapshot(a.device,a.output)
    elif a.mode=='approve':review_import(a.device,a.output)
    else:execute(a.device,a.mode,a.output)
