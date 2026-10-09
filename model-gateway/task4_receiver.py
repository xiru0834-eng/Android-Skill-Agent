"""Fresh receiver setup and bounded historical-export smoke, not the Task 4 primary score."""
import argparse
import json
from pathlib import Path
from workflow_experiment import ROOT,adb,write
from task4_files import SERIAL,ARTIFACTS,gate,state,snapshot,click,receive_package
from task4_protocol import package_bytes,fingerprint,canonical
from workflow_contract import compile_evidence
from task2_protocol import FLOWS,INITIALS
from task4_execution import fixture,read_display,set_display,display_proof,start
from task4_transfer import restore_commands
from task3_audit import rejudge
import task3_device_checks as device
from named_journey_device import home
from transfer_run import private
from entry_preflight import application_service_state


def install(out):
    if adb(SERIAL,'emu','avd','name').splitlines()[0].strip()!='Task4Transfer':raise RuntimeError('WRONG_RECEIVER')
    if adb(SERIAL,'shell','getprop','sys.boot_completed').strip()!='1':raise RuntimeError('BOOT_NOT_READY')
    if adb(SERIAL,'shell','pm','list','packages','edu.sydney').strip():raise RuntimeError('RECEIVER_NOT_FRESH')
    for package,(_,relative) in ARTIFACTS.items():
        if adb(SERIAL,'emu','avd','name').splitlines()[0].strip()!='Task4Transfer':raise RuntimeError('WRONG_RECEIVER')
        raw=adb(SERIAL,'install',str(ROOT/relative),timeout=60)
        write(out/(package+'-install.json'),dict(raw=raw,apkSha256=fingerprint((ROOT/relative).read_bytes())))
        if 'Success' not in raw:raise RuntimeError('INSTALL_NOT_CONFIRMED:'+package)
    write(out/'device.json',gate('Task4Transfer'))


def enable(out):
    gate('Task4Transfer');adb(SERIAL,'shell','am','start','-W','-a','android.settings.ACCESSIBILITY_SETTINGS')
    snapshot(out,'accessibility-list');click(lambda n:n.get('text')=='Demo Probe')
    ui=snapshot(out,'accessibility-detail');switch=[n for n in ui.iter('node') if n.get('resource-id')=='android:id/switch_widget']
    if len(switch)!=1:raise RuntimeError('ACCESSIBILITY_SWITCH_NOT_UNIQUE')
    if switch[0].get('checked')!='true':
        click(lambda n:n.get('resource-id')=='com.android.settings:id/main_switch_bar')
        snapshot(out,'normal-permission-dialog');click(lambda n:n.get('resource-id')=='com.android.settings:id/permission_enable_allow_button')
    home(SERIAL);ui=snapshot(out,'connected')
    if application_service_state(ui) is not True:raise RuntimeError('SERVICE_NOT_CONNECTED')
    write(out/'permission.json',dict(normalSettingsUI=True,connected=True,secureSettingsWritten=False,paidCalls=0))


def archived(flow):
    if flow not in FLOWS:raise ValueError('UNKNOWN_ARCHIVE_FLOW')
    source=ROOT/'output/autonomous-five/task-2'/('files-v36-'+flow)
    recording=ROOT/'output/autonomous-five/task-2/emulator-journey-v36-r2'/(flow+'-recording')
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    pack=read(source/'expected-package.json');trace=read(recording/'trace.json')
    filename='named-workflow-'+pack['skill']['traceSha256'][:8]+'.json';blob=(source/filename).read_bytes()
    package_bytes(blob,pack)
    if (canonical(compile_evidence(trace))!=canonical(pack['skill']) or read(recording/'named-package.json')!=pack
        or [s['id'] for s in trace['steps']]!=FLOWS[flow] or trace['source']!='AUTOMATED'
        or fingerprint(blob)!=read(source/'export-score.json')['sha256']
        or 'Skill exported.' not in (source/'export-confirmed.xml').read_text(encoding='utf-8')):raise ValueError('ARCHIVED_ORIGINAL_NOT_PROVEN')
    return dict(flow=flow,package=pack,file=str(source/filename),sha256=fingerprint(blob),sourceAvd='PortableSkill',source=str(source.relative_to(ROOT)))


def restore_receiver(original,out):
    gate('Task4Transfer')
    for cmd in restore_commands(original['state']):adb(SERIAL,'shell',*cmd)
    after=read_display();write(out/'display-after.json',after)
    restored=after['state']==original['state'];write(out/'restoration.json',dict(restored=restored,paidCalls=0))
    if not restored:raise RuntimeError('DISPLAY_NOT_RESTORED')


def smoke(out):
    write(out/'device.json',gate('Task4Transfer'));original=read_display();write(out/'display-before.json',original)
    before=state();write(out/'before.json',before);rows=[];where=out
    plan=[dict(id=f'A-{f}-i{i}',flow=f,display='D0',appearance='native',group='archive',initial=initial[:]) for f in FLOWS for i,initial in enumerate(INITIALS)]
    plan +=[dict(id='A-R-'+d,flow='R',display=d,appearance='native',group='archive',initial=INITIALS[0][:]) for d in ['D1','D2','D3']]
    write(out/'planned-smoke.json',dict(cases=plan,primarySlotsAffected=0,maximumRuns=12))
    try:
        for f in FLOWS:
            item=archived(f);where=out/(f+'-import');where.mkdir();write(where/'archived-source.json',item)
            receive_package(item['package'],Path(item['file']),where)
            print('ARCHIVED ORIGINAL RECEIVED '+f,flush=True)
        label=None
        for row in plan:
            where=out/row['id'];where.mkdir();item=archived(row['flow']);skill=item['package']['skill']
            if label!=row['display']:set_display(row['display']);label=row['display']
            case_id,prior=fixture(row,skill);write(where/'case.json',dict(row,caseId=case_id));write(where/'before.json',prior)
            display_proof(row,where)
            try:previous=private(SERIAL,'edu.sydney.probe','recorded-workflow-result.json')['runId']
            except RuntimeError as error:
                if 'No such file' not in str(error):raise
                previous=None
            start(skill);result,oracle,journal,samples,disk=device.collect(skill,row['initial'],case_id,where,previous)
            checked=rejudge(skill,row['initial'],result,oracle,journal,samples,disk,case_id);write(where/'score.json',checked)
            rows.append(dict(id=row['id'],correctCompletion=checked['correctCompletion'],evidenceQualified=checked['evidenceQualified'],elapsedMs=checked['elapsedMs'],falseSuccess=checked['falseSuccess']))
            write(out/'rows.json',rows);print(row['id']+' '+str(checked['correctCompletion'])+' '+str(checked['errors']),flush=True)
            if not checked['correctCompletion']:raise RuntimeError('ARCHIVED_PROCESS_NOT_CORRECT')
    except Exception as error:
        write(where/'failure.json',dict(reason=str(error)));write(out/'failure.json',dict(reason=str(error),stage=where.name,paidCalls=0))
        try:snapshot(where,'failure')
        except Exception:pass
        raise
    finally:
        restore_receiver(original,out)
        write(out/'after.json',state())


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['install','enable','smoke']);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve()
    if not out.is_relative_to(ROOT/'output/autonomous-five/task-4') or out.exists():p.error('NEW Task 4 evidence directory required')
    out.mkdir(parents=True)
    try:globals()[a.mode](out)
    except Exception as e:
        write(out/'command-failure.json',dict(reason=str(e),paidCalls=0));raise
