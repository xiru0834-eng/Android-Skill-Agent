"""Normal DocumentsUI import, with before-approval and after-approval evidence."""
import argparse
import json
import re
import time
from pathlib import Path
from named_journey_device import prefs,library,tap,snap
from workflow_capture import tree
from workflow_experiment import adb,write

def initial_preferences(serial,read=prefs):
    try:return read(serial)
    except RuntimeError as error:
        # Android creates this namespace only after its first real preference write.
        if 'shared_prefs/recorded_workflows.xml: No such file or directory' in str(error):return {}
        raise

def import_package(serial,file,out,picker_open=False,expect_conflict=False):
    out.mkdir(parents=True,exist_ok=False)
    pack=json.loads(file.read_text(encoding='utf-8'))
    before=initial_preferences(serial);write(out/'before.json',before)
    adb(serial,'push',str(file),'/sdcard/Download/'+file.name)
    if not picker_open:library(serial);tap(serial,'libraryImport')
    ui=tree(serial)
    matches=[n for n in ui.iter('node') if n.get('resource-id')=='android:id/title' and n.get('text')==file.name]
    if len(matches)!=1:raise RuntimeError('File must be visible and unique in local Downloads')
    b=list(map(int,re.findall(r'-?\d+',matches[0].get('bounds',''))))
    adb(serial,'shell','input','tap',(b[0]+b[2])//2,(b[1]+b[3])//2);time.sleep(1)
    snap(serial,out/'import-confirmation.png');tap(serial,'button1','android')
    pending=prefs(serial);write(out/'pending.json',pending)
    assert pending.get('library')==before.get('library') and pending.get('approved')==before.get('approved')
    assert json.loads(pending['pendingNamed'])==pack and pending.get('result')==before.get('result')
    library(serial);tap(serial,'libraryReview');snap(serial,out/'review-confirmation.png');tap(serial,'button1','android')
    # A normal button click returns before the UI thread commits on a busy emulator.
    # Observe completion; never click Save twice to make a check pass.
    deadline=time.monotonic()+8
    while True:
        after=prefs(serial)
        saved=pack in json.loads(after.get('library','[]')) and 'pendingNamed' not in after
        if expect_conflict or saved or time.monotonic()>=deadline:break
        time.sleep(.2)
    write(out/'after.json',after)
    if expect_conflict:
        assert after.get('library')==before.get('library') and after.get('approved')==before.get('approved')
        assert after.get('pendingNamed')==pending.get('pendingNamed')
    else:
        assert pack in json.loads(after['library']) and 'pendingNamed' not in after
    assert after.get('result')==before.get('result')
    snap(serial,out/'review-result.png')
    write(out/'score.json',dict(unchangedBeforeApproval=True,noExecution=True,conflictRejected=expect_conflict,saved=not expect_conflict))
    print('IMPORT CHECK PASS '+file.name,flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('file',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--device',default='emulator-5554');p.add_argument('--picker-open',action='store_true');p.add_argument('--expect-conflict',action='store_true');a=p.parse_args()
    import_package(a.device,a.file,a.output,a.picker_open,a.expect_conflict)
