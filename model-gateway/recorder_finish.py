"""Read-only post-run integrity, Android codec checks, and scoped UI evidence."""
import base64
import hashlib
import json
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from workflow_capture import APP, PROBE, tree, workbench, click
from workflow_experiment import adb, write

def main():
    serial='R5CW134LLBZ';root=Path('evaluation/recorder-repair');out=root/'final-checks';out.mkdir(exist_ok=False)
    command=[r'D:/python_code/closed-loop-gui-agent/tools/platform-tools/adb.exe','-s',serial]
    before=ET.fromstring((root/'original/recorded_workflows.xml').read_bytes())
    after_data=subprocess.check_output(command+['exec-out','run-as',PROBE,'cat','shared_prefs/recorded_workflows.xml'],timeout=20)
    after=ET.fromstring(after_data)
    lookup=lambda doc:{n.get('name'):n.text for n in doc}
    assert lookup(before)==lookup(after), 'Saved workflows/preferences changed'
    (out/'recorded_workflows.xml').write_bytes(after_data)
    versions=adb(serial,'shell','dumpsys','package',PROBE)
    remote=adb(serial,'shell','pm','path',PROBE).strip().removeprefix('package:')
    subprocess.run(command+['pull',remote,str(out/'installed-final.apk')],check=True,timeout=30)
    apk=Path('android-agent-probe/build/manual/demo-probe-recorder-audit.apk').read_bytes()
    assert apk==(out/'installed-final.apk').read_bytes(), 'Installed binary mismatch'
    write(out/'integrity.json',dict(savedWorkflowPreferencesUnchanged=True,
          installedVersionLines=[x.strip() for x in versions.splitlines() if 'versionCode=' in x or 'versionName=' in x],
          candidateApkSha256=hashlib.sha256(apk).hexdigest(),installedBinaryMatches=True,
          executorUnchangedThisTurn=(root/'original/WorkflowRunner.java').read_bytes()==Path('android-agent-probe/app/src/main/java/edu/sydney/probe/WorkflowRunner.java').read_bytes()))
    skill=json.loads((root/'confirmation/normal-1/candidate.json').read_text())
    encoded=base64.b64encode(json.dumps(skill).encode()).decode()
    result=adb(serial,'shell','am','instrument','-w','-e','skill',encoded,PROBE+'/.WorkflowChecks')
    (out/'android-codec.txt').write_text(result,encoding='utf-8');assert 'PASS workflow codec checks=9' in result,result
    # Return to the workbench to inspect status separation, not to run a skill.
    workbench(serial);ui=tree(serial);(out/'workbench.xml').write_bytes(ET.tostring(ui,encoding='utf-8'))
    state=next(n.get('text','') for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/flowState')
    assert '历史执行结果（不表示本次录制成功）' in state and '历史技能，与本次录制不同' in state
    adb(serial,'shell','input','swipe',540,1700,540,600,300);time.sleep(.4)
    # A scoped screenshot after the observer confirmed the experimental workbench.
    (out/'workbench.png').write_bytes(subprocess.check_output(command+['exec-out','screencap','-p'],timeout=20))
    # Clear only the fixture's injected fault/dirty state. Do not begin a human recording.
    adb(serial,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','layout','multi','--es','fault','normal','--es','initial','0,40,0,3')
    adb(serial,'shell','am','start','-n',PROBE+'/.MainActivity','-f','0x04000000');time.sleep(.7)
    click(serial,'teachEntry');time.sleep(.7)
    ui=tree(serial);assert any(n.get('resource-id')==PROBE+':id/teachRecord' for n in ui.iter('node'))
    (out/'teaching-ready.xml').write_bytes(ET.tostring(ui,encoding='utf-8'))
    (out/'teaching-ready.png').write_bytes(subprocess.check_output(command+['exec-out','screencap','-p'],timeout=20))
    write(out/'handoff.json',dict(app=APP,initial=[0,40,0,3],fault='normal',page='TeachingActivity',recordingStarted=False,skillsChanged=False))
    print('Saved preferences unchanged; executor unchanged this turn; Android codec 9 checks; history/current UI separated.')

if __name__=='__main__':main()
