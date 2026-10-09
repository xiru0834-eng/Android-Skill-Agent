"""Preserve scoped recorder evidence before reproduction; never prints private prefs."""
import hashlib
import json
import subprocess
from pathlib import Path

ADB = r'D:/python_code/closed-loop-gui-agent/tools/platform-tools/adb.exe'
SERIAL = 'R5CW134LLBZ'

def main():
    out = Path('evaluation/recorder-repair/original')
    out.mkdir(parents=True, exist_ok=False)
    def capture(name, *args):
        data = subprocess.check_output([ADB, '-s', SERIAL, *args], timeout=40)
        (out / name).write_bytes(data)
        return data
    for ident in ('73df88d9-b24c-4d07-9651-880781277689', '2de2c2cb-976f-4336-a9d7-723ac66127db', 'b9ea3d1f-19cd-4b6a-af9c-24f0bad8928a'):
        capture(ident+'.json', 'exec-out', 'run-as', 'edu.sydney.probe', 'cat', 'files/workflow-trace-'+ident+'.json')
    capture('latest-trace.json','exec-out','run-as','edu.sydney.probe','cat','files/workflow-trace.json')
    capture('oracle.json','exec-out','run-as','edu.sydney.transferlab','cat','files/workflow-oracle.json')
    capture('recorded_workflows.xml','exec-out','run-as','edu.sydney.probe','cat','shared_prefs/recorded_workflows.xml')
    remote = subprocess.check_output([ADB,'-s',SERIAL,'shell','pm','path','edu.sydney.probe'],text=True).strip().removeprefix('package:')
    subprocess.run([ADB,'-s',SERIAL,'pull',remote,str(out/'installed-before.apk')],check=True,timeout=40)
    sources = Path('android-agent-probe/app/src/main/java/edu/sydney/probe')
    for name in ('WorkflowRecorder.java','WorkflowUi.java','WorkflowActivity.java','TeachingActivity.java','TeachingOverlay.java','WorkflowRunner.java'):
        (out/name).write_bytes((sources/name).read_bytes())
    manifest={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
    (out/'sha256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('Preserved',len(manifest),'scoped evidence/source files; original APK hash:',manifest['installed-before.apk'])

if __name__=='__main__':main()
