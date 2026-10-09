"""Re-import archived real skills through normal picker; execute without editing originals."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import task3_device_checks as device
from task2_file_checks import visible_click,await_import_state
from transfer_audit import evaluate
from recovery_evidence import audit_route
from task3_protocol import judge
from task3_audit import audit_envelope,identity_types
from workflow_experiment import write
from safe_probe_upgrade import adb_bytes


def identity_proof(skill,result,oracle,journal,samples):
    try:
        return (not audit_envelope(result,oracle,samples) and not identity_types(result,journal)
                and result['traceId']==skill['traceId'] and result['traceSha256']==skill['traceSha256']
                and bool(journal) and journal[0]['kind']=='START' and journal[0]['data']==skill
                and all(e['runId']==result['runId'] for e in journal)
                and [e['seq'] for e in journal]==list(range(1,len(journal)+1))
                and journal[-1]['kind']=='RESULT' and journal[-1]['data']==result
                and sum(e['kind']=='RESULT' and e['data'].get('status')!='RUNNING' for e in journal)==1)
    except (KeyError,TypeError,IndexError):return False


def choose_download(file):
    ui=device.tree(device.SERIAL)
    if not any(n.get('resource-id')=='android:id/title' and n.get('text')==file for n in ui.iter('node')):
        visible_click(lambda n:n.get('content-desc') in ['Show roots','显示根目录','显示位置'])
        visible_click(lambda n:n.get('text') in ['Downloads','下载'] and n.get('resource-id')=='android:id/title')
    until=time.monotonic()+6
    while time.monotonic()<until:
        ui=device.tree(device.SERIAL)
        if any(n.get('resource-id')=='android:id/title' and n.get('text')==file for n in ui.iter('node')):break
        time.sleep(.2)
    else:raise RuntimeError('PUBLIC_FILE_NOT_VISIBLE')
    visible_click(lambda n:n.get('resource-id')=='android:id/title' and n.get('text')==file)


def import_original(item,out):
    out.mkdir(parents=True,exist_ok=False)
    pack=dict(kind='NAMED_WORKFLOW',version=1,name=item['name'],skill=item['skill'])
    file='task3-legacy-'+item['skill']['traceSha256'][:12]+'.json'
    if file in device.adb(device.SERIAL,'shell','ls','/sdcard/Download').splitlines():raise RuntimeError('DO_NOT_OVERWRITE_PUBLIC_FILE')
    write(out/file,pack);write(out/'original-entry.json',item)
    device.adb(device.SERIAL,'push',str(out/file),'/sdcard/Download/'+file)
    raw=adb_bytes(device.SERIAL,'exec-out','cat','/sdcard/Download/'+file)
    if raw!=(out/file).read_bytes():raise RuntimeError('PUBLIC_FILE_BYTES_DIFFER')
    before=device.prefs(device.SERIAL);write(out/'before.json',before)
    device.library(device.SERIAL);device.management_control('libraryTools');device.management_control('libraryImport')
    choose_download(file)
    device.review_controls(device.tree(device.SERIAL));device.tap(device.SERIAL,'button1','android')
    pending=await_import_state(pack,before);write(out/'pending.json',pending)
    device.library(device.SERIAL);device.management_control('libraryTools');device.management_control('libraryReview')
    device.review_controls(device.tree(device.SERIAL));device.snap(device.SERIAL,out/'local-review.png');device.tap(device.SERIAL,'button1','android')
    after=await_import_state(pack,before,reviewed=True);write(out/'after.json',after)
    write(out/'import-score.json',dict(normalPicker=True,localReview=True,approvalIsolated=True,originalSkillUnchanged=True,
                                     publicFileSha256=hashlib.sha256(raw).hexdigest(),originalDeviceExport=False,paidCalls=0))


def run(originals,out):
    out.mkdir(parents=True,exist_ok=False);write(out/'device.json',device.gate())
    source=device.source_hashes();extra=[Path(__file__),Path(__file__).with_name('task3_audit.py')]
    source.update({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in extra});write(out/'source-hashes.json',source)
    state=json.loads(originals.read_text(encoding='utf-8'));catalog=json.loads(state['library']);approved=json.loads(state['approved'])
    items=[e for e in catalog if e['skill']['version']==2][:2]+[e for e in catalog if e['skill']==approved]
    if len(items)!=3:raise RuntimeError('OLD_SKILL_SET_UNAVAILABLE')
    before=device.prefs(device.SERIAL);write(out/'new-avd-before.json',before);rows=[]
    try:
        for n,item in enumerate(items):
            import_original(item,out/f'old-{n}-import')
            where=out/f'old-{n}-run';where.mkdir();skill=item['skill'];initial=[0,40,0,3]
            case_id,fixture=device.fixture(skill,initial);write(where/'before.json',fixture);write(where/'case.json',dict(caseId=case_id,initial=initial))
            previous=device.private(device.SERIAL,device.PROBE,'recorded-workflow-result.json')['runId']
            device.start_run(skill);result,oracle,journal,samples,disk=device.collect(skill,initial,case_id,where,previous)
            judged=evaluate(oracle,result,skill['finalGoals'],[dict(capturedMs=x['events'][-1]['ms'],oracle=x) for x in samples],case_id=case_id,run_id=result['runId'])
            route=judge(skill,initial,result,oracle,journal,samples,disk,case_id) if skill['version']==3 else audit_route(result,skill)
            identity=identity_proof(skill,result,oracle,journal,samples)
            okay=identity and judged['confirmed_success'] and disk==oracle['events'][-1]['saved'] and (route['correctCompletion'] if skill['version']==3 else route['valid'])
            checked=dict(correctCompletion=bool(okay),identity=identity,final=judged,route=route,oldVersion=skill['version'],paidCalls=0)
            write(where/'score.json',checked);rows.append(dict(name=item['name'],version=skill['version'],correctCompletion=bool(okay),elapsedMs=result['finishedMs']-result['startedMs']))
            write(out/'results.json',rows);print('OLD '+item['name']+' '+str(okay),flush=True)
            if not okay:raise RuntimeError('LEGACY_REGRESSION_NOT_CORRECT')
        after=device.prefs(device.SERIAL);old_entries=json.loads(before['library'])
        preserved=all(e in json.loads(after['library']) for e in old_entries)
        write(out/'new-avd-preservation.json',dict(oldEntriesKept=preserved,oldCount=len(old_entries),newCount=len(json.loads(after['library'])),originalAvdUntouched=True))
        if not preserved:raise RuntimeError('NEW_AVD_SKILLS_CHANGED')
    except Exception as error:
        write(out/'failure.json',dict(reason=str(error),paidCalls=0));raise
    finally:
        expected=device.source_hashes();expected.update({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in extra})
        write(out/'source-stability.json',dict(sourceStable=expected==source))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--originals',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(a.originals,a.output)
