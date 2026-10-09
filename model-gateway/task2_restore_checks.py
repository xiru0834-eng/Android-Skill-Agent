"""Read-only original-archive checks plus normal UI language restoration."""
import argparse
import json
from pathlib import Path
from safe_probe_upgrade import device_manifest
from named_journey_device import prefs,home,tap,snap
from workflow_capture import tree,PROBE
from workflow_experiment import adb,write

SERIAL='emulator-5554'
# Live pointers legitimately change when teaching/running; their originals remain backed up.
LIVE={'shared_prefs/recorded_workflows.xml','shared_prefs/teaching_journey.xml',
      'files/workflow-trace.json','files/recorded-workflow-result.json'}


def main():
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--originals',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    if adb(SERIAL,'emu','avd','name').splitlines()[0].strip()!='PortableSkill':raise RuntimeError('WRONG_AVD')
    original=json.loads(a.originals.read_text(encoding='utf-8'));current=prefs(SERIAL)
    library=json.loads(current['library']);old=json.loads(original['library'])
    if not all(e in library for e in old):raise RuntimeError('ORIGINAL_LIBRARY_LOST_OR_CHANGED')
    if json.loads(current['approved'])!=json.loads(original['approved']):raise RuntimeError('ORIGINAL_APPROVAL_NOT_RESTORED')
    before=json.loads(a.manifest.read_text(encoding='utf-8'));after=device_manifest(SERIAL)
    missing=sorted(before.keys()-after.keys());changed=sorted(k for k in before if k in after and before[k]!=after[k])
    unexpected=sorted(set(changed)-LIVE)
    write(a.output/'manifest-after.json',after)
    verdict=dict(originalFiles=len(before),unchangedOriginalFiles=sum(after.get(k)==v for k,v in before.items()),
                 missing=missing,changedLivePointers=sorted(set(changed)&LIVE),unexpectedChangedOriginals=unexpected,
                 originalLibraryPreserved=True,originalActiveApprovalRestored=True,oldCount=len(old),newCount=len(library),paidCalls=0)
    write(a.output/'originals.json',verdict)
    if missing or unexpected:raise RuntimeError('UNEXPECTED_ORIGINAL_FILE_CHANGE')
    home(SERIAL);tap(SERIAL,'teachEntry');ui=tree(SERIAL)
    switches=[n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/teachLanguage']
    if len(switches)!=1:raise RuntimeError('LANGUAGE_CONTROL_UNCONFIRMED')
    if switches[0].get('text')=='中文':tap(SERIAL,'teachLanguage')
    ui=tree(SERIAL)
    if not any(n.get('resource-id')==PROBE+':id/teachLanguage' and n.get('text')=='English' for n in ui.iter('node')):
        raise RuntimeError('CHINESE_UI_NOT_RESTORED')
    if any(n.get('resource-id')==PROBE+':id/teachStop' for n in ui.iter('node')):raise RuntimeError('RECORDING_STILL_ACTIVE')
    result=json.loads(prefs(SERIAL)['result'])
    if result['status']=='RUNNING':raise RuntimeError('TASK_STILL_RUNNING')
    home(SERIAL);snap(SERIAL,a.output/'restored-home.png')
    display=dict(size=adb(SERIAL,'shell','wm','size').strip(),density=adb(SERIAL,'shell','wm','density').strip(),
                 fontScale=adb(SERIAL,'shell','settings','get','system','font_scale').strip(),chineseUi=True,
                 recordingActive=False,taskRunning=False)
    write(a.output/'display-and-ui.json',display);print(json.dumps(verdict),flush=True)


if __name__=='__main__':main()
