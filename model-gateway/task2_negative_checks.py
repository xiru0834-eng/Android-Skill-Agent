"""Twelve frozen teaching counterexamples through emulator UI; no new approvals."""
import argparse
import json
import re
import time
from pathlib import Path
from task2_device_checks import SERIAL,prepare_teaching
from named_journey_device import prefs,tap,text,home,snap
from flexible_device_checks import fixture,target_tap
from workflow_capture import PROBE,tree
from workflow_experiment import adb,write
from transfer_run import private
from workflow_contract import compile_evidence,WorkflowError

PROTECTED=('approved','library','namedSkill','name','draft','pendingNamed','result','storageUnconfirmed')


def protected_unchanged(before,after):
    return all(before.get(key)==after.get(key) for key in PROTECTED)


def stopped_invalid(trace):
    if trace.get('end')!='STOPPED' or trace.get('source')!='AUTOMATED':return False
    try:compile_evidence(trace)
    except (WorkflowError,ValueError):return True
    return False


def start(actions,out):
    fixture(dict(page='overview'),[0,40,0,3]);prepare_teaching(language='en')
    text(SERIAL,'teachName','T2 negative check');text(SERIAL,'teachGoal','Keep evidence; never approve incomplete or conflicting recordings.')
    tap(SERIAL,'teachRecord');tap(SERIAL,'button1','android')
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        trace=private(SERIAL,PROBE,'workflow-trace.json')
        if trace.get('error'):raise RuntimeError('NEGATIVE_BASELINE_FAILED:'+trace['error'])
        if trace.get('initial'):break
        time.sleep(.2)
    else:raise RuntimeError('NEGATIVE_BASELINE_TIMEOUT')
    for number,key in enumerate(actions,1):
        target_tap(key);deadline=time.monotonic()+7
        while time.monotonic()<deadline:
            trace=private(SERIAL,PROBE,'workflow-trace.json')
            if trace.get('error'):raise RuntimeError('NEGATIVE_RECORDING_NOT_TRIGGERED:'+trace['error'])
            if len(trace['steps'])==number:break
            time.sleep(.2)
        else:raise RuntimeError('NEGATIVE_STEP_UNCONFIRMED:'+key)
    home(SERIAL);tap(SERIAL,'teachEntry');tap(SERIAL,'teachStop')
    trace=private(SERIAL,PROBE,'workflow-trace.json');write(out/'trace.json',trace)
    return trace


def invalid_recordings(out,rows):
    actions={'empty':[], 'all_cancelled':['wfOpenLamp','wfLampValue80','wfLampCancel'],
             'unfinished_page':['wfOpenLamp','wfLampValue80']}
    for category,keys in actions.items():
        for repeat in range(2):
            path=out/f'E-{category}-{repeat}';path.mkdir()
            before=prefs(SERIAL);write(path/'before.json',before)
            trace=start(keys,path);ui=tree(SERIAL)
            title=next(n.get('text') for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/teachStateTitle')
            offered=any(n.get('resource-id') in [PROBE+':id/teachGenerate',PROBE+':id/teachSave'] and n.get('enabled')=='true' for n in ui.iter('node'))
            after=prefs(SERIAL);write(path/'after.json',after);snap(SERIAL,path/'incomplete.png')
            handling=(stopped_invalid(trace) and [s['id'] for s in trace['steps']]==keys
                      and title=='Recording ended · incomplete' and not offered)
            row=dict(id=path.name,outcome='PASS' if handling and protected_unchanged(before,after) else 'FAIL',
                     facts=dict(triggered=True,expectedHandling=handling,oldStateProtected=protected_unchanged(before,after),
                                noExecution=before.get('result')==after.get('result')),nativeUi=True,source='AUTOMATED')
            rows.append(row);write(out/'results.json',rows)
            print('NEGATIVE '+row['id']+' '+row['outcome'],flush=True)
            if row['outcome']!='PASS':raise RuntimeError('NEGATIVE_INCOMPLETE_NOT_HANDLED')


def review_cases(out,rows):
    preparation=out/'review-draft';preparation.mkdir()
    trace=start(['wfOpenLamp','wfLampValue80','wfLampSave'],preparation)
    before=prefs(SERIAL);tap(SERIAL,'teachGenerate')
    draft=json.loads(prefs(SERIAL,'teaching_journey')['draft'])
    if draft!=compile_evidence(trace) or not protected_unchanged(before,prefs(SERIAL)):
        raise RuntimeError('UNREVIEWED_DRAFT_CHANGED_APPROVAL')
    write(preparation/'skill.json',draft)
    duplicate=json.loads(before['library'])[0]['name']
    for category in ['cancel_review','invalid_save','duplicate_name']:
        for repeat in range(2):
            path=out/f'E-{category}-{repeat}';path.mkdir();before=prefs(SERIAL)
            write(path/'before.json',before);tap(SERIAL,'teachSave');snap(SERIAL,path/'review.png')
            if category=='cancel_review':tap(SERIAL,'button2','android')
            else:
                value='x'*61 if category=='invalid_save' else duplicate
                text(SERIAL,'teachSaveName',value);ui=tree(SERIAL)
                actual=[n.get('text') for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/teachSaveName']
                if actual!=[value]:raise RuntimeError('SAVE_NAME_WAS_TRUNCATED')
                tap(SERIAL,'button1','android')
            after=prefs(SERIAL);write(path/'after.json',after);snap(SERIAL,path/'handled.png');ui=tree(SERIAL)
            shown='\n'.join(n.get('text','') for n in ui.iter('node'))
            expected=category=='cancel_review' or ('NAME_LENGTH' in shown if category=='invalid_save' else 'Not saved: duplicate name' in shown)
            same=protected_unchanged(before,after)
            row=dict(id=path.name,outcome='PASS' if expected and same else 'FAIL',
                     facts=dict(triggered=True,expectedHandling=expected,oldStateProtected=same,
                                noExecution=before.get('result')==after.get('result')),nativeUi=True,source='AUTOMATED')
            rows.append(row);write(out/'results.json',rows)
            print('NEGATIVE '+row['id']+' '+row['outcome'],flush=True)
            if row['outcome']!='PASS':raise RuntimeError('NEGATIVE_REVIEW_NOT_HANDLED')


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    try:
        if adb(SERIAL,'emu','avd','name').splitlines()[0].strip()!='PortableSkill':raise RuntimeError('WRONG_AVD')
        if not re.search(r'\bversionCode=36\b',adb(SERIAL,'shell','dumpsys','package',PROBE)):raise RuntimeError('WRONG_CANDIDATE')
        rows=[];invalid_recordings(a.output,rows);review_cases(a.output,rows)
    except Exception as error:
        write(a.output/'failure.json',dict(reason=str(error),paidCalls=0))
        try:snap(SERIAL,a.output/'failure.png')
        except Exception:pass
        raise


if __name__=='__main__':main()
