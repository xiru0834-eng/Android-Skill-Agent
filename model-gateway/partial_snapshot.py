"""Capture current binaries/sources without credentials or old evaluation bundles."""
import hashlib,shutil
from pathlib import Path
from workflow_experiment import adb,write
from named_journey_device import prefs
import json

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=Path('evaluation/partial-workflow/implementation-snapshot');out.mkdir(exist_ok=False);files=[]
    for folder in ['android-agent-probe/app/src/main','android-agent-probe/tests','android-transfer-bench/app/src/main','evaluation/android-observer/app/src/main']:
        files.extend(p for p in Path(folder).rglob('*') if p.is_file())
    files+=list(Path('model-gateway').glob('*.py'))
    files+=list(map(Path,['android-agent-probe/build-offline.ps1','android-agent-probe/test-core.ps1','tasks/partial-workflow-design.md','android-agent-probe/build/manual/demo-probe-partial-dev.apk']))
    hashes={}
    for p in files:
        dest=out/'files'/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest);hashes[p.as_posix()]=digest(dest)
    installed={}
    for serial in ['R5CW134LLBZ','emulator-5554']:
        installed[serial]={}
        for pkg in ['edu.sydney.probe','edu.sydney.transferlab','edu.sydney.evaluation']:
            path=adb(serial,'shell','pm','path',pkg).strip().removeprefix('package:');dest=out/'installed'/serial/(pkg+'.apk');dest.parent.mkdir(parents=True,exist_ok=True)
            adb(serial,'pull',path,str(dest));installed[serial][pkg]=digest(dest)
        assert installed[serial]['edu.sydney.probe']==digest(Path('android-agent-probe/build/manual/demo-probe-partial-dev.apk'))
        entries=json.loads(prefs(serial)['library']);original=json.loads(Path('evaluation/user-recording-100/saved-skill.json').read_text(encoding='utf-8'))
        assert any(e['skill']==original for e in entries)
    write(out/'manifest.json',dict(files=hashes,installed=installed,note='Fingerprint captured during confirmation tests. Not a claim of pre-run sealing; APK unchanged since final v24 build. Original skill still present on both devices.'))
    print('Snapshot: matching installed APKs; original skills preserved',flush=True)

if __name__=='__main__':main()
