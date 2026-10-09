"""Original public-file transfer via ordinary export/import/review UI, owned AVDs only."""
import json
import re
import time
import xml.etree.ElementTree as ET
import task3_device_checks as device
from named_journey_device import prefs,library,snap
from workflow_experiment import adb,write,ROOT
from workflow_capture import PROBE,APP
from safe_probe_upgrade import adb_bytes
from task2_file_checks import await_import_state
from task4_protocol import source_record,package_bytes,fingerprint
from task4_transfer import chain_check

SERIAL='emulator-5554'
ARTIFACTS={PROBE:(40,'android-agent-probe/build/manual/demo-probe-v40-failure-context.apk'),
 APP:(6,'android-transfer-bench/build/manual/transfer-bench-task3-v6.apk'),
 'edu.sydney.evaluation':(4,'evaluation/android-observer/build/manual/observer-task3-v4.apk')}


def gate(avd):
    if adb(SERIAL,'shell','getprop','sys.boot_completed').strip()!='1':raise RuntimeError('BOOT_NOT_READY')
    if avd not in ['Task3Workflows','Task4Transfer'] or adb(SERIAL,'emu','avd','name').splitlines()[0].strip()!=avd:raise RuntimeError('WRONG_OWNED_AVD')
    actual={}
    for package,(version,relative) in ARTIFACTS.items():
        raw=adb(SERIAL,'shell','dumpsys','package',package)
        if not re.search(r'\bversionCode='+str(version)+r'\b',raw):raise RuntimeError('WRONG_PACKAGE_VERSION:'+package)
        location=adb(SERIAL,'shell','pm','path',package).strip().removeprefix('package:')
        sha=adb(SERIAL,'shell','sha256sum',location).split()[0]
        if sha!=fingerprint((ROOT/relative).read_bytes()):raise RuntimeError('WRONG_PACKAGE_BYTES:'+package)
        actual[package]=dict(version=version,apkSha256=sha)
    return dict(avd=avd,serial=SERIAL,artifacts=actual,paidCalls=0)


def state():return device.optional_prefs()


def visible_node(ui,predicate):
    """Text rows require a clickable ancestor; never click an offscreen rectangle."""
    windows=list(ui)
    found=[n for n in ui.iter('node') if predicate(n)]
    if len(windows)!=1 or len(found)!=1:raise RuntimeError('FILE_CONTROL_NOT_UNIQUE')
    parents={c:p for p in ui.iter() for c in p}
    target=found[0];ancestor=target
    while ancestor.get('clickable')!='true' and ancestor in parents:ancestor=parents[ancestor]
    window=list(map(int,re.findall(r'-?\d+',windows[0].get('bounds',''))))
    box=list(map(int,re.findall(r'-?\d+',target.get('bounds',''))))
    if (len(window)!=4 or len(box)!=4 or target.get('enabled')!='true' or ancestor.get('clickable')!='true' or ancestor.get('enabled')!='true'
        or not(window[0]<=box[0]<box[2]<=window[2] and window[1]<=box[1]<box[3]<=window[3])):
        raise RuntimeError('FILE_CONTROL_NOT_VISIBLE_OR_CLICKABLE')
    return box


def click(predicate):
    box=visible_node(device.tree(SERIAL),predicate)
    adb(SERIAL,'shell','input','tap',(box[0]+box[2])//2,(box[1]+box[3])//2);time.sleep(.5)


def snapshot(out,name):
    snap(SERIAL,out/(name+'.png'));return ET.parse(out/(name+'.xml')).getroot()


def wait_marker(marker,out,name):
    until=time.monotonic()+8
    while time.monotonic()<until:
        ui=device.tree(SERIAL)
        if time.monotonic()>=until:break
        if any(marker in n.get('text','') for n in ui.iter('node')):
            snapshot(out,name);return
        time.sleep(.2)
    raise RuntimeError('UI_ACK_MISSING:'+marker)


def downloads():
    ui=device.tree(SERIAL)
    if not any(n.get('text')=='Downloads' for n in ui.iter('node')):
        click(lambda n:n.get('content-desc')=='Show roots')
        click(lambda n:n.get('resource-id')=='android:id/title' and n.get('text')=='Downloads')


def export_one(flow,out):
    out.mkdir(parents=True,exist_ok=False);record=source_record(flow);pack=record['package']
    begun=time.monotonic();timings=[]
    write(out/'source-record.json',record);write(out/'device.json',gate('Task3Workflows'))
    before=state();write(out/'before.json',before)
    entries=json.loads(before['library']);indices=[i for i,e in enumerate(entries) if e==pack]
    if len(indices)!=1:raise RuntimeError('ORIGINAL_REVIEWED_PACKAGE_NOT_UNIQUE')
    filename='named-workflow-'+pack['skill']['traceSha256'][:8]+'.json'
    write(out/'file.json',dict(filename=filename,sourceAvd='Task3Workflows',flow=flow))
    if filename in adb(SERIAL,'shell','ls','/sdcard/Download').splitlines():raise RuntimeError('DO_NOT_OVERWRITE_PUBLIC_FILE')
    library(SERIAL);device.management_control('libraryExport'+str(indices[0]));downloads()
    ui=snapshot(out,'export-picker')
    timings.append(dict(stage='exportPreparation',hostStartMs=round(begun*1000),hostEndMs=round(time.monotonic()*1000)));write(out/'stage-times.json',timings)
    if not any(n.get('text')==filename and n.get('class')=='android.widget.EditText' for n in ui.iter('node')):raise RuntimeError('EXPORT_FILENAME_DIFFERS')
    click(lambda n:n.get('text','').upper()=='SAVE' and n.get('resource-id')=='android:id/button1')
    wait_marker('Skill exported.',out,'export-ack');click(lambda n:n.get('resource-id')=='android:id/button1')
    timings.append(dict(stage='exportAcknowledged',hostStartMs=timings[-1]['hostEndMs'],hostEndMs=round(time.monotonic()*1000)));write(out/'stage-times.json',timings)
    blob=adb_bytes(SERIAL,'exec-out','cat','/sdcard/Download/'+filename);package_bytes(blob,pack)
    (out/filename).write_bytes(blob);after=state();write(out/'after.json',after)
    if after!=before:raise RuntimeError('SOURCE_STATE_CHANGED_BY_EXPORT')
    write(out/'export.json',dict(sha256=fingerprint(blob),bytes=len(blob),normalPicker=True,paidCalls=0))
    print('EXPORTED ORIGINAL '+flow+' '+filename,flush=True)


def receive_one(flow,source,out):
    out.mkdir(parents=True,exist_ok=False);original=source/flow
    pack=source_record(flow)['package'];meta=json.loads((original/'file.json').read_text(encoding='utf-8'))
    filename=meta['filename']
    if filename!='named-workflow-'+pack['skill']['traceSha256'][:8]+'.json':raise ValueError('UNSAFE_OR_DIFFERENT_PUBLIC_FILENAME')
    blob=(original/filename).read_bytes();package_bytes(blob,pack)
    write(out/'file.json',meta)
    receive_package(pack,original/filename,out)
    proof=load_chain(original,out);score=chain_check(pack,proof);write(out/'chain-score.json',score)
    if not score['correctChain']:raise RuntimeError('TRANSFER_CHAIN_NOT_CORRECT:'+str(score['errors']))
    print('RECEIVED / LOCALLY REVIEWED ORIGINAL '+flow,flush=True)


def receive_package(pack,original_file,out):
    """Also usable for explicitly separate historical-file diagnostics."""
    filename=original_file.name
    if filename!='named-workflow-'+pack['skill']['traceSha256'][:8]+'.json':raise ValueError('UNSAFE_OR_DIFFERENT_PUBLIC_FILENAME')
    blob=original_file.read_bytes();package_bytes(blob,pack)
    timings=[];begun=time.monotonic()
    write(out/'device.json',gate('Task4Transfer'))
    if filename in adb(SERIAL,'shell','ls','/sdcard/Download').splitlines():raise RuntimeError('DO_NOT_OVERWRITE_PUBLIC_FILE')
    adb(SERIAL,'push',str(original_file),'/sdcard/Download/'+filename)
    received=adb_bytes(SERIAL,'exec-out','cat','/sdcard/Download/'+filename)
    (out/filename).write_bytes(received)
    if received!=blob:raise RuntimeError('TRANSFER_BYTES_CHANGED')
    timings.append(dict(stage='copyAndReadback',hostStartMs=round(begun*1000),hostEndMs=round(time.monotonic()*1000)));write(out/'stage-times.json',timings)
    write(out/'transport.json',dict(byteCount=len(received),sourceSha256=fingerprint(blob),targetSha256=fingerprint(received),hostTimingOnly=True,paidCalls=0))
    before=state();write(out/'before.json',before)
    library(SERIAL);device.management_control('libraryTools');device.management_control('libraryImport')
    ui=device.tree(SERIAL)
    if not any(n.get('resource-id')=='android:id/title' and n.get('text')==filename for n in ui.iter('node')):downloads()
    snapshot(out,'import-picker');click(lambda n:n.get('resource-id')=='android:id/title' and n.get('text')==filename)
    wait_marker('Import draft:',out,'import-preview');device.review_controls(device.tree(SERIAL))
    timings.append(dict(stage='importPreview',hostStartMs=timings[-1]['hostEndMs'],hostEndMs=round(time.monotonic()*1000)));write(out/'stage-times.json',timings)
    click(lambda n:n.get('resource-id')=='android:id/button1')
    pending=await_import_state(pack,before,read=state);write(out/'pending.json',pending)
    timings.append(dict(stage='pendingAcknowledged',hostStartMs=timings[-1]['hostEndMs'],hostEndMs=round(time.monotonic()*1000)));write(out/'stage-times.json',timings)
    library(SERIAL);device.management_control('libraryTools');device.management_control('libraryReview')
    device.review_controls(device.tree(SERIAL));snapshot(out,'local-review');click(lambda n:n.get('resource-id')=='android:id/button1')
    after=await_import_state(pack,before,reviewed=True,read=state);write(out/'after.json',after)
    timings.append(dict(stage='localReviewAcknowledged',hostStartMs=timings[-1]['hostEndMs'],hostEndMs=round(time.monotonic()*1000)));write(out/'stage-times.json',timings)


def load_chain(source,target):
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    filename=read(source/'file.json')['filename']
    if not re.fullmatch(r'named-workflow-[a-f0-9]{8}\.json',filename):raise ValueError('UNSAFE_PUBLIC_FILENAME')
    return dict(sourceAvd=read(source/'device.json')['avd'],targetAvd=read(target/'device.json')['avd'],
        sourceBlob=(source/filename).read_bytes(),targetBlob=(target/filename).read_bytes(),
        sourceBefore=read(source/'before.json'),sourceAfter=read(source/'after.json'),
        before=read(target/'before.json'),pending=read(target/'pending.json'),after=read(target/'after.json'),
        exportXml=(source/'export-ack.xml').read_text(encoding='utf-8'),importXml=(target/'import-preview.xml').read_text(encoding='utf-8'),
        reviewXml=(target/'local-review.xml').read_text(encoding='utf-8'))
