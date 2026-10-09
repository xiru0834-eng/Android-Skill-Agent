"""Frozen same-App skill portability; independent fixture scoring, no model calls."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import statistics
import time

from phone_reuse import d, reset_fixture, prepare_targets
from contracts import load_json, require

ROOT = Path(__file__).resolve().parents[1]
JOB = ROOT/'evaluation/gpt-skills/compiler-dev-v1/1-observed'
PROFILES = {'native': ('1080x2400', 420), 'size': ('900x2000', 420), 'density': ('1080x2400', 360)}


def schedule(reps):
    rng = random.Random(928)
    rows = []
    for profile in PROFILES:
        cases = [(name, list(initial), 'normal') for name, initial in
                 [('FF',(False,False)), ('TF',(True,False)), ('FT',(False,True)), ('TT',(True,True))]]
        if profile == 'native':
            cases += [(name, [False,False], name) for name in ('missing_second','duplicate_second')]
        batch = [dict(profile=profile, name=name, initial=initial, mode=mode,
                      negative=mode!='normal', rep=rep) for rep in range(1,reps+1)
                 for name,initial,mode in cases]
        rng.shuffle(batch)
        for case in batch:
            methods = ['skill','coordinate']; rng.shuffle(methods)
            rows.extend(dict(case, method=method) for method in methods)
    return rows


def score(case, state, report):
    actual = state['target'] is True and state['other'] is True
    expected = [0,0] if case['negative'] else [int(not v) for v in case['initial']]
    clicks = [state['targetClicks'], state['otherClicks']]
    issued = report['inputs'] if case['method']=='skill' else 2
    # A tap on empty space is still an unnecessary issued input, even when
    # neither fixture counter increments (particularly in negative cases).
    extra = max(sum(max(0,a-b) for a,b in zip(clicks,expected)), issued-sum(expected))
    match = clicks == expected and issued == sum(expected)
    if case['method']=='skill':
        confirmed = report['status']=='SUCCEEDED'
        passed = (report.get('desired')==[True,True] and match and
                  (report['status']=='REFUSED' if case['negative'] else confirmed and actual))
        false_success = confirmed and not actual
    else:
        confirmed = false_success = None
        passed = not case['negative'] and actual and match
    return dict(actualGoal=actual, confirmed=confirmed, falseSuccess=false_success,
                expectedClicks=expected, observedClicks=clicks, issuedInputs=issued,
                extraInputs=extra, inputsMatch=match, **{'pass':passed})


def summary(rows):
    result = dict(completed=len(rows))
    for method in ('skill','coordinate'):
        selected = [r for r in rows if r['case']['method']==method]
        positive = [r for r in selected if not r['case']['negative']]
        negative = [r for r in selected if r['case']['negative']]
        times = sorted(r['report']['elapsedMs'] for r in positive) if method=='skill' else []
        result[method] = dict(total=len(selected), positive=len(positive),
            actual=sum(r['actualGoal'] for r in positive), positivePass=sum(r['pass'] for r in positive),
            negative=len(negative), negativePass=sum(r['pass'] for r in negative),
            falseSuccess=sum(r['falseSuccess'] for r in selected) if method=='skill' else None,
            extraInputs=sum(r['extraInputs'] for r in selected),
            p50ms=statistics.median(times) if times else None,
            p95ms=times[math.ceil(.95*len(times))-1] if times else None)
    return result


def reviewed_skill():
    return json.loads(d.s.prefs('two_step_skills')['skill.'+d.BENCH])


def approve(skill, out):
    require(json.loads(d.s.prefs('two_step_skills')['draft.'+d.BENCH]) == skill, 'DRAFT_CHANGED')
    reset_fixture('normal', [False,False])
    d.two_screen(); time.sleep(1); d.s.click('twoCheck'); time.sleep(1.2)
    require(d.s.prefs('two_step_skills').get('reason.'+d.BENCH)=='READY', 'CHECK_FAILED')
    d.two_screen(); time.sleep(1); d.s.click('twoReview')
    message = d.s.find(resource='android:id/message').get('text','')
    require(all(s['resourceId'] in message for s in skill['steps']), 'REVIEW_MISMATCH')
    require(d.s.find(resource='android:id/button1').get('text','').casefold()=='save', 'SAVE_BUTTON')
    d.s.click('button1', pkg='android'); time.sleep(.4)
    require(reviewed_skill()==skill, 'REVIEW_NOT_SAVED')
    d.s.save(out/'review.json', dict(skill=skill, userAuthorized=True, normalUi=True, preferenceWrites=False))


def display():
    return {key:d.s.adb('shell','wm',key).strip() for key in ('size','density')}


def restore_display(original):
    for key in ('size','density'):
        match = re.search(r'Override \w+:\s*(\S+)', original[key])
        d.s.adb('shell','wm',key,match.group(1) if match else 'reset')


def profile_config(profile):
    size, density = PROFILES[profile]
    d.s.adb('shell','wm','size',size)
    d.s.adb('shell','wm','density',density)
    time.sleep(1)
    current=display()
    require(current['size'].split(':')[-1].strip()==size, 'SIZE_NOT_APPLIED')
    require(current['density'].split(':')[-1].strip()==str(density), 'DENSITY_NOT_APPLIED')
    return current


def foreground_bench():
    state=d.s.adb('shell','dumpsys','activity','activities')
    require(any('topResumedActivity=' in line and d.BENCH+'/' in line for line in state.splitlines()),
            'BENCH_NOT_FOREGROUND')


def run_case(case, points, skill, out, position):
    before=reset_fixture(case['mode'],case['initial']); report=None
    if case['method']=='skill':
        require(reviewed_skill()==skill,'APPROVED_SKILL_CHANGED')
        d.two_screen(); time.sleep(.5)
        state=d.s.find(resource=d.s.PROBE+':id/twoState').get('text','')
        require('Service ON' in state and 'recording=false' in state, 'SERVICE_NOT_READY')
        def controls():
            tree=d.s.ui()
            return [d.s.S.find(tree,resource=d.s.PROBE+f':id/twoTarget{i}') for i in range(2)]
        prep=prepare_targets([True,True],controls,d.s.S.tap_node)
        d.s.save(out/f'{position:03d}-prepared.json',dict(case=case,before=before,preparation=prep))
        previous=d.s.prefs('skills').get('last_result')
        wall=time.monotonic(); d.s.click('twoRun')
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            raw=d.s.prefs('skills').get('last_result')
            if raw and raw!=previous and json.loads(raw)['status']!='RUNNING':
                report=json.loads(raw); break
            time.sleep(.1)
        if report is None: raise RuntimeError('No terminal result; no retry')
    else:
        time.sleep(.5); foreground_bench()
        d.s.save(out/f'{position:03d}-prepared.json',dict(case=case,before=before,points=points))
        wall=time.monotonic()
        for x,y in points:
            foreground_bench()
            d.s.adb('shell','input','tap',x,y); time.sleep(.25)
        time.sleep(.6)
    after=d.oracle()
    return dict(case=case,before=before,after=after,report=report,
                driverWallMs=round((time.monotonic()-wall)*1000,2),**score(case,after,report))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--approve',action='store_true')
    parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--allow-experiment',action='store_true')
    args=parser.parse_args()
    require(args.allow_experiment,'EXPERIMENT_CONSENT_REQUIRED')
    require(os.environ.get('ANDROID_SERIAL')=='emulator-5554','EXPLICIT_EMULATOR_ONLY')
    require(d.s.adb('shell','getprop','ro.kernel.qemu').strip()=='1','NOT_EMULATOR')
    source=JOB/'skill-v2.json'; skill=load_json(source.read_text(encoding='utf-8'))
    require(skill['appPackage']==d.BENCH,'BENCH_ONLY')
    original=display(); out=args.output; out.mkdir(parents=True,exist_ok=False)
    save=lambda name,value:d.s.save(out/name,value)
    save('before.json',dict(display=original,prefs=d.s.prefs('two_step_skills'),
                           accessibility=d.s.adb('shell','settings','get','secure','enabled_accessibility_services')))
    shutil.copy2(source,out/'source-skill.json')
    for name in ('emulator_transfer.py','test_emulator_transfer.py','phone_reuse.py'):
        shutil.copy2(Path(__file__).with_name(name),out/name)
    rows=[]
    try:
        if args.approve: approve(skill,out)
        require(reviewed_skill()==skill,'APPROVED_SKILL_MISMATCH')
        profile_config('native'); reset_fixture('normal',[False,False]); time.sleep(.5)
        tree=d.s.ui(); points=[]
        for name in ('mainToggle','otherToggle'):
            node=d.s.S.find(tree,resource=d.BENCH+':id/'+name)
            x1,y1,x2,y2=map(int,re.findall(r'\d+',node.get('bounds')))
            require(x2>x1 and y2>y1,'INVISIBLE_CALIBRATION')
            points.append([(x1+x2)//2,(y1+y2)//2])
        cases=schedule(1 if args.smoke else 5)
        files=[source,ROOT/'android-agent-probe/build/manual/demo-probe-evidence-dev.apk',
               ROOT/'android-transfer-bench/build/manual/transfer-bench-debug.apk',Path(__file__)]
        save('protocol.json',dict(stage='development' if args.smoke else 'confirmation',
             seed=928,planned=len(cases),cases=cases,profiles=PROFILES,originalDisplay=original,
             serial=os.environ['ANDROID_SERIAL'],sourceSkill=str(source),
             hashes={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
             coordinatePoints=points,coordinateCalibration='emulator native; fixed thereafter; not Samsung pixels',
             modelCalls=0,latency='skill Android elapsedMs includes launch wait; excludes setup, review, import; coordinate not latency-comparable'))
        current=None
        for position,case in enumerate(cases,1):
            if case['profile']!=current:
                save('display-'+case['profile']+'.json',profile_config(case['profile']))
                current=case['profile']
                reset_fixture('normal',[False,False]);time.sleep(.5)
                save('layout-'+current+'.json',[n.attrib for n in d.s.ui().iter('node')])
                d.s.snapshot(out/('layout-'+current+'.png'))
            row=run_case(case,points,skill,out,position);rows.append(row)
            save(f'{position:03d}-result.json',row)
            save('summary.json',summary(rows))
            print(json.dumps(dict(position=position,profile=case['profile'],case=case['name'],
                 method=case['method'],passed=row['pass'],actual=row['actualGoal'],
                 status=row['report']['status'] if row['report'] else 'NO_SELF_REPORT')),flush=True)
        require(source.read_bytes()==(out/'source-skill.json').read_bytes(),'SOURCE_CHANGED')
        require(reviewed_skill()==skill,'SKILL_CHANGED_AT_END')
        save('integrity.json',dict(sourceUnchanged=True,approvedSkillUnchanged=True))
    except Exception as error:
        save('failure.json',dict(errorType=type(error).__name__,reason=str(error),completed=len(rows)))
        raise
    finally:
        save('summary.json',summary(rows))
        restore_display(original)
        save('restored-display.json',display())
        reset_fixture('normal',[False,False])


if __name__=='__main__': main()
