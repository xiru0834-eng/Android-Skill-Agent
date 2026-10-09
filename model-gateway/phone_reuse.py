"""User-authorized review via UI, then bounded independent-oracle phone development trials."""
import argparse
import json
from pathlib import Path
import random
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'evaluation/trace-evidence'))
import device_suite as d
from contracts import load_json, require
from parameter_gate import prepare_targets


def judge(case, report, oracle):
    actual = [oracle['target'], oracle['other']] == case['desired']
    negative = case['mode'] in ('missing_second', 'duplicate_second')
    counts = [0, 0] if negative else [int(a != b) for a,b in zip(case['initial'], case['desired'])]
    received = report.get('desired') == case['desired']
    inputs_ok = [oracle['targetClicks'], oracle['otherClicks']] == counts and report['inputs'] == sum(counts)
    passed = received and inputs_ok and (report['status'] == 'REFUSED' if negative else report['status'] == 'SUCCEEDED' and actual)
    return dict(actualGoal=actual, falseSuccess=report['status'] == 'SUCCEEDED' and not actual,
                requestReceived=received, expectedClicks=counts, inputsMatch=inputs_ok, **{'pass':passed})


def reset_fixture(mode, initial):
    # Negative tests intentionally have missing/duplicate nodes. Reset via the
    # fixture-only channel and read its oracle; never require positive UI shape.
    d.s.adb('shell','am','start','-n',d.BENCH+'/.MainActivity','--ez','setup','true',
            '--es','mode',mode,'--ez','initial',str(initial[0]).lower(),
            '--ez','otherInitial',str(initial[1]).lower())
    for _ in range(8):
        state = d.oracle()
        if (state['mode'] == mode and [state['target'],state['other']] == list(initial)
                and state['targetClicks'] == state['otherClicks'] == 0): return state
        time.sleep(.1)
    raise RuntimeError('Fixture reset not confirmed; no execution started')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--user-approved-review-and-test', action='store_true')
    args = parser.parse_args(); require(args.user_approved_review_and_test, 'REVIEW_AUTHORIZATION_REQUIRED')
    skill = load_json((args.job/'skill-v2.json').read_text(encoding='utf-8'))
    require(skill['appPackage'] == d.BENCH, 'BENCH_ONLY')
    current = d.s.prefs('two_step_skills')
    require(json.loads(current['draft.'+d.BENCH]) == skill and current.get('origin.'+d.BENCH) == 'true', 'DRAFT_CHANGED')
    args.output.mkdir(parents=True, exist_ok=False)
    save = lambda name,value: d.s.save(args.output/name, value)
    save('before.json', current)
    for name in ('phone_reuse.py', 'test_phone_reuse.py'):
        shutil.copy2(Path(__file__).with_name(name), args.output/name)
    cases = [dict(name=name, initial=list(initial), desired=list(desired), mode=mode)
             for name,initial,desired,mode in [
                 ('both_on',(False,False),(True,True),'normal'),
                 ('both_off',(True,True),(False,False),'normal'),
                 ('mixed_target',(True,False),(False,True),'normal'),
                 ('partial_skip',(True,False),(True,True),'normal'),
                 ('already',(True,True),(True,True),'normal'),
                 ('moved',(False,False),(True,True),'moved'),
                 ('missing',(False,False),(True,True),'missing_second'),
                 ('duplicate',(False,False),(True,True),'duplicate_second')]]
    schedule = []; rng = random.Random(482)
    for rep in (1,2,3):
        batch = [dict(c, rep=rep) for c in cases]; rng.shuffle(batch); schedule.extend(batch)
    save('protocol.json', dict(scope='phone development, same approved v2 skill; not R/S comparison',
                               source='ADB_TEST', review='user-authorized UI save by test driver',
                               modelCallsDuringReplay=0, seed=482, planned=24, cases=schedule,
                               latencyScope='Android execution only; excludes teaching/compiler/review/preparation'))
    rows=[]
    try:
        d.fixture(); d.two_screen(); time.sleep(1); d.s.click('twoCheck'); time.sleep(1.2)
        require(d.s.prefs('two_step_skills').get('reason.'+d.BENCH) == 'READY', 'CHECK_NOT_READY')
        d.two_screen(); time.sleep(1); d.s.click('twoReview')
        message = d.s.find(resource='android:id/message').get('text', '')
        require(all(s['resourceId'] in message for s in skill['steps']), 'REVIEW_CHANGED')
        require(d.s.find(resource='android:id/button1').get('text', '').casefold() == 'save', 'SAVE_BUTTON')
        d.s.click('button1', pkg='android'); time.sleep(.4)
        require(json.loads(d.s.prefs('two_step_skills')['skill.'+d.BENCH]) == skill, 'SAVE_FAILED')
        save('review.json', dict(userAuthorized=True, uiSaved=True, noPreferenceWrites=True, skill=skill))
        for position,case in enumerate(schedule, 1):
            before = reset_fixture(case['mode'], case['initial'])
            d.two_screen(); time.sleep(.5)
            def controls():
                tree=d.s.ui()
                return [d.s.S.find(tree,resource=d.s.PROBE+f':id/twoTarget{i}') for i in range(2)]
            preparation = prepare_targets(case['desired'], controls, d.s.S.tap_node)
            save(f'{position:02d}-prepared.json', dict(case=case, preparation=preparation, before=before))
            previous=d.s.prefs('skills').get('last_result'); d.s.click('twoRun')
            for _ in range(90):
                raw=d.s.prefs('skills').get('last_result')
                if raw and raw != previous and json.loads(raw)['status'] != 'RUNNING': break
                time.sleep(.1)
            else: raise RuntimeError('Execution result timeout; no input retry')
            report=json.loads(raw); after=d.oracle()
            row=dict(case=case, result=report, before=before, after=after, **judge(case,report,after))
            rows.append(row);save(f'{position:02d}-result.json',row)
            print(json.dumps(dict(position=position, case=case['name'], rep=case['rep'], passed=row['pass'],
                                  status=report['status'], inputs=report['inputs'], elapsedMs=report['elapsedMs'])),flush=True)
    except Exception as error:
        save('failure.json', dict(errorType=type(error).__name__,reason=str(error),completed=len(rows)))
        raise
    finally:
        save('summary.json', dict(planned=24, completed=len(rows), passed=sum(r['pass'] for r in rows),
                                  falseSuccess=sum(r['falseSuccess'] for r in rows), rows=rows))


if __name__ == '__main__': main()
