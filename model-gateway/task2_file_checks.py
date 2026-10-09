"""Normal-file chain diagnostics on the source emulator, not cross-device proof."""
import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from named_journey_device import prefs,library,tap,snap
from workflow_capture import tree,PROBE
from workflow_experiment import adb,write
from task2_protocol import file_match
from safe_probe_upgrade import adb_bytes

SERIAL='emulator-5554'


def management_tap(key):
    """Normal large scrolls of Probe management UI, never target-task recovery."""
    for attempt in range(20):
        ui=tree(SERIAL);found=[n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/'+key]
        if len(found)>1:raise RuntimeError('MANAGEMENT_CONTROL_AMBIGUOUS')
        panels=[n for n in ui.iter('node') if n.get('class')=='android.widget.ScrollView']
        if len(panels)!=1:raise RuntimeError('MANAGEMENT_SCROLL_NOT_UNIQUE')
        panel=list(map(int,re.findall(r'-?\d+',panels[0].get('bounds',''))))
        if len(panel)!=4 or panel[3]<=panel[1]:raise RuntimeError('MANAGEMENT_SCROLL_NOT_READY')
        target=None
        if found:
            target=list(map(int,re.findall(r'-?\d+',found[0].get('bounds',''))))
            if (len(target)==4 and target[2]>target[0] and target[3]>target[1]
                and panel[1]<=target[1] and target[3]<=panel[3] and found[0].get('enabled')=='true'):
                tap(SERIAL,key);return
        if attempt==19:break
        x=(panel[0]+panel[2])//2;high=int(panel[1]+.12*(panel[3]-panel[1]));low=int(panel[1]+.88*(panel[3]-panel[1]))
        above=bool(target and len(target)==4 and target[3]<=panel[1] and target[3]>target[1])
        adb(SERIAL,'shell','input','swipe',x,high if above else low,x,low if above else high,400)
        time.sleep(.3)
    raise RuntimeError('MANAGEMENT_CONTROL_UNREACHABLE')


def await_import_state(expected,before,reviewed=False,read=lambda:prefs(SERIAL),clock=time.monotonic,sleep=time.sleep):
    end=clock()+8
    while clock()<end:
        current=read()
        if clock()>=end:break
        if current.get('storageUnconfirmed')=='true':raise RuntimeError('IMPORT_STORAGE_UNCONFIRMED')
        if not reviewed:
            if any(current.get(k)!=before.get(k) for k in ['approved','library','result','draft']):
                raise RuntimeError('IMPORT_TRANSFERRED_APPROVAL_OR_CHANGED_DRAFT')
            if json.loads(current.get('pendingNamed','null'))==expected:return current
        else:
            if current.get('result')!=before.get('result'):raise RuntimeError('IMPORT_EXECUTED_A_TASK')
            if ('pendingNamed' not in current and json.loads(current.get('approved','null'))==expected['skill']
                and expected in json.loads(current.get('library','[]'))):return current
        sleep(.2)
    raise RuntimeError('IMPORT_ACKNOWLEDGEMENT_TIMEOUT')


def visible_click(predicate):
    ui=tree(SERIAL);nodes=[n for n in ui.iter('node') if predicate(n)]
    if len(nodes)!=1:raise RuntimeError('FILE_CONTROL_NOT_UNIQUE')
    b=list(map(int,re.findall(r'-?\d+',nodes[0].get('bounds',''))))
    if len(b)!=4 or b[2]<=b[0] or b[3]<=b[1] or nodes[0].get('enabled')!='true':raise RuntimeError('FILE_CONTROL_NOT_READY')
    adb(SERIAL,'shell','input','tap',(b[0]+b[2])//2,(b[1]+b[3])//2)


def open_export(recording,out):
    pack=json.loads((recording/'named-package.json').read_text(encoding='utf-8'))
    before=prefs(SERIAL);entries=json.loads(before['library'])
    indices=[i for i,e in enumerate(entries) if e==pack]
    if len(indices)!=1:raise RuntimeError('SAVED_PACKAGE_NOT_UNIQUE')
    file='named-workflow-'+pack['skill']['traceSha256'][:8]+'.json'
    existing=adb(SERIAL,'shell','ls','/sdcard/Download').splitlines()
    if file in existing:raise RuntimeError('DO_NOT_OVERWRITE_EXISTING_EXPORT')
    write(out/'before.json',before);write(out/'expected-package.json',pack)
    write(out/'file-protocol.json',dict(filename=file,sourceDevice=SERIAL,sameDeviceOnly=True,paidCalls=0))
    library(SERIAL);management_tap('libraryExport'+str(indices[0]));snap(SERIAL,out/'export-picker.png')
    print('NORMAL EXPORT PICKER OPEN: '+file,flush=True)


def finish_export(out):
    protocol=json.loads((out/'file-protocol.json').read_text(encoding='utf-8'));file=protocol['filename']
    ui=tree(SERIAL)
    if not any(n.get('text')==file and n.get('class')=='android.widget.EditText' for n in ui.iter('node')):
        raise RuntimeError('PICKER_FILENAME_DIFFERS')
    if not any(n.get('text')=='Downloads' for n in ui.iter('node')):raise RuntimeError('PICKER_NOT_DOWNLOADS')
    visible_click(lambda n:n.get('text','').upper()=='SAVE' and n.get('clickable')=='true')
    end=time.monotonic()+8
    while time.monotonic()<end:
        ui=tree(SERIAL)
        if any('Skill exported.' in n.get('text','') for n in ui.iter('node')):break
    else:raise RuntimeError('EXPORT_NOT_CONFIRMED')
    snap(SERIAL,out/'export-confirmed.png');tap(SERIAL,'button1','android')
    blob=adb_bytes(SERIAL,'exec-out','cat','/sdcard/Download/'+file)
    expected=json.loads((out/'expected-package.json').read_text(encoding='utf-8'))
    if json.loads(blob)!=expected:raise RuntimeError('EXPORTED_PACKAGE_MISMATCH')
    (out/file).write_bytes(blob)
    write(out/'export-score.json',dict(normalPicker=True,semanticEqual=True,bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),
          approvalExported=False,hashComparedAcrossDevices=False,modelCalls=0))
    print('EXPORT PASS: '+file,flush=True)


def same_device_import(out):
    file=json.loads((out/'file-protocol.json').read_text(encoding='utf-8'))['filename']
    expected=json.loads((out/'expected-package.json').read_text(encoding='utf-8'));before=prefs(SERIAL)
    library(SERIAL);management_tap('libraryTools');management_tap('libraryImport');snap(SERIAL,out/'import-picker.png')
    visible_click(lambda n:n.get('resource-id')=='android:id/title' and n.get('text')==file)
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        ui=tree(SERIAL)
        if any('Import draft:' in n.get('text','') for n in ui.iter('node')):break
    else:raise RuntimeError('IMPORT_PREVIEW_UNCONFIRMED')
    snap(SERIAL,out/'import-preview.png');tap(SERIAL,'button1','android')
    pending=await_import_state(expected,before);write(out/'pending.json',pending)
    if any(pending.get(k)!=before.get(k) for k in ['approved','library','result','draft']):raise RuntimeError('IMPORT_TRANSFERRED_APPROVAL_OR_CHANGED_DRAFT')
    if json.loads(pending['pendingNamed'])!=expected:raise RuntimeError('PENDING_PACKAGE_MISMATCH')
    library(SERIAL);management_tap('libraryTools');management_tap('libraryReview');snap(SERIAL,out/'target-local-review.png');tap(SERIAL,'button1','android')
    after=await_import_state(expected,before,reviewed=True);write(out/'after.json',after)
    if 'pendingNamed' in after or expected not in json.loads(after['library']):raise RuntimeError('LOCAL_REVIEW_NOT_PERSISTENT')
    if after.get('result')!=before.get('result'):raise RuntimeError('IMPORT_EXECUTED_A_TASK')
    blob=adb_bytes(SERIAL,'exec-out','cat','/sdcard/Download/'+file)
    if not file_match((out/file).read_bytes(),blob):raise RuntimeError('FILE_BYTES_CHANGED')
    write(out/'import-score.json',dict(normalPicker=True,unreviewedPending=True,approvalIsolated=True,
          reviewRequired=True,reviewDidNotExecute=True,byteHashExact=True,sameDeviceOnly=True,crossDeviceConfirmed=False,paidCalls=0))
    print('SAME-DEVICE FILE IMPORT/REVIEW PASS: '+file,flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['open','export','import']);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--recording',type=Path);a=p.parse_args()
    if a.mode=='open':a.output.mkdir(parents=True,exist_ok=False)
    try:
        if adb(SERIAL,'emu','avd','name').splitlines()[0].strip()!='PortableSkill':raise RuntimeError('WRONG_AVD')
        if not re.search(r'\bversionCode=36\b',adb(SERIAL,'shell','dumpsys','package','edu.sydney.probe')):raise RuntimeError('WRONG_VERSION')
        if a.mode=='open':open_export(a.recording,a.output)
        elif a.mode=='export':finish_export(a.output)
        else:same_device_import(a.output)
    except Exception as error:
        write(a.output/('failure-'+a.mode+'.json'),dict(error=type(error).__name__,reason=str(error),paidCalls=0))
        try:snap(SERIAL,a.output/('failure-'+a.mode+'.png'))
        except Exception:pass
        raise


if __name__=='__main__':main()
