"""Record exact installed binaries and source snapshot; credentials excluded."""
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from workflow_experiment import adb,write
from named_journey_device import prefs

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    out=Path('evaluation/named-journey/implementation-snapshot');out.mkdir(exist_ok=False)
    files=[]
    for folder in ['android-agent-probe/app/src/main','android-agent-probe/tests','android-transfer-bench/app/src/main','evaluation/android-observer/app/src/main']:
        files.extend(p for p in Path(folder).rglob('*') if p.is_file())
    files.extend(Path('model-gateway').glob('*.py'))
    files.extend(map(Path,['android-agent-probe/build-offline.ps1','android-agent-probe/test-core.ps1','tasks/named-skill-journey-design.md',
        'android-agent-probe/build/manual/demo-probe-named-dev.apk','evaluation/android-observer/build/manual/observer-named-dev.apk']))
    hashes={}
    for p in files:
        dest=out/'files'/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest);hashes[p.as_posix()]=digest(dest)
    installed={}
    for s in ['R5CW134LLBZ','emulator-5554']:
        installed[s]={}
        for pkg in ['edu.sydney.probe','edu.sydney.transferlab','edu.sydney.evaluation']:
            remote=adb(s,'shell','pm','path',pkg).strip().removeprefix('package:');dest=out/'installed'/s/(pkg+'.apk');dest.parent.mkdir(parents=True,exist_ok=True)
            adb(s,'pull',remote,str(dest));installed[s][pkg]=digest(dest)
        assert installed[s]['edu.sydney.probe']==digest(Path('android-agent-probe/build/manual/demo-probe-named-dev.apk'))
        assert installed[s]['edu.sydney.evaluation']==digest(Path('evaluation/android-observer/build/manual/observer-named-dev.apk'))
        approved=json.loads(prefs(s)['library']);original=json.loads(Path('evaluation/user-recording-100/saved-skill.json').read_text(encoding='utf-8'))
        assert any(e['skill']==original for e in approved)
    write(out/'manifest.json',dict(files=hashes,installed=installed,note='Post-build/post-phone-test fingerprint verification, not a pre-registered timestamp. APK unchanged since final build; both installed binaries match. Original skill is preserved in both catalogs.'))
    tests=[('java-tests.txt',['powershell','-NoProfile','-ExecutionPolicy','Bypass','-File','android-agent-probe/test-core.ps1']),
        ('python-tests.txt',[sys.executable,'-m','unittest','discover','-s','model-gateway','-p','test_*.py'])]
    for name,cmd in tests:
        r=subprocess.run(cmd,capture_output=True);(out/name).write_bytes(r.stdout+r.stderr)
        if r.returncode:raise RuntimeError('Regression failed '+name)
    print('Installed binaries match source build; originals preserved; test logs saved',flush=True)

if __name__=='__main__':main()
