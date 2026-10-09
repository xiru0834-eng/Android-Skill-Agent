"""Require a live service, preserved skills and normal fixture before user handoff."""
import json
import argparse
import hashlib
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from workflow_capture import APP,PROBE,click,tree
from workflow_experiment import adb,write

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    serial='R5CW134LLBZ';out=args.output;out.mkdir(exist_ok=False)
    state=adb(serial,'shell','dumpsys','accessibility')
    bound=state.split('Bound services:',1)[-1].split('Enabled services:',1)[0]
    assert 'edu.sydney.probe/.ProbeService' in bound,'Probe service is not bound'
    original=ET.fromstring(Path('evaluation/recorder-repair/original/recorded_workflows.xml').read_bytes())
    current=ET.fromstring(adb(serial,'shell','run-as',PROBE,'cat','shared_prefs/recorded_workflows.xml'))
    fields=lambda root:{x.get('name'):x.text for x in root}
    assert fields(original)==fields(current),'Saved skills changed'
    adb(serial,'shell','am','start','-n',PROBE+'/.MainActivity','-f','0x04000000');time.sleep(.7)
    click(serial,'teachEntry');time.sleep(1)
    ui=tree(serial);(out/'teaching.xml').write_bytes(ET.tostring(ui,encoding='utf-8'))
    status=next(n.get('text','') for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/teachStatus')
    assert '未连接' not in status and 'disconnected' not in status,'UI reports service disconnected'
    assert '自动化测试记录（不是你的新示范）' in status,'UI lost automated-test provenance'
    trace=json.loads(adb(serial,'shell','run-as',PROBE,'cat','files/workflow-trace.json'))
    assert trace['end']!='RECORDING','Unexpected active recording'
    oracle=json.loads(adb(serial,'shell','run-as',APP,'cat','files/workflow-oracle.json'))
    assert oracle['fault']=='normal' and oracle['events'][-1]['saved']==[0,40,0,3]
    cmd=[r'D:/python_code/closed-loop-gui-agent/tools/platform-tools/adb.exe','-s',serial]
    remote=adb(serial,'shell','pm','path',PROBE).strip().removeprefix('package:')
    subprocess.run(cmd+['pull',remote,str(out/'installed.apk')],check=True,timeout=30)
    apk=Path('android-agent-probe/build/manual/demo-probe-record-origin.apk').read_bytes()
    assert apk==(out/'installed.apk').read_bytes(),'Installed APK differs'
    (out/'teaching.png').write_bytes(subprocess.check_output(cmd+['exec-out','screencap','-p'],timeout=20))
    write(out/'handoff.json',dict(serviceBound=True,uiServiceConnected=True,skillsUnchanged=True,recording=False,fixtureNormal=True,
        initial=[0,40,0,3],latestRecordIsAutomated=True,apkSha256=hashlib.sha256(apk).hexdigest()))
    print('READY: service bound, UI connected, saved skills unchanged, no recording, normal fixture.')

if __name__=='__main__':main()
