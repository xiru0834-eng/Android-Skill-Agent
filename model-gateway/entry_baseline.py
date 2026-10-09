"""Scoped reversible baseline; credentials and pairing preferences are excluded."""
import hashlib
import json
import shutil
from pathlib import Path
from named_journey_device import prefs
from workflow_experiment import adb, write

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'output/entry-hardening-v1/baseline'

def sha(data):return hashlib.sha256(data).hexdigest()

def freeze():
    OUT.mkdir(parents=True,exist_ok=False)
    sources=list((ROOT/'model-gateway').glob('*.py'))+list((ROOT/'android-agent-probe/app/src/main').rglob('*'))
    sources=[p for p in sources if p.is_file()]
    manifest={}
    for p in sources:
        rel=p.relative_to(ROOT);dest=OUT/'source'/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,dest);manifest[str(rel)]=sha(p.read_bytes())
    values=prefs('R5CW134LLBZ')
    write(OUT/'workflow-prefs.json',values)
    package_path=adb('R5CW134LLBZ','shell','pm','path','edu.sydney.probe').strip()
    if not package_path.startswith('package:/data/app/') or '\n' in package_path:raise ValueError('APK_PATH')
    adb('R5CW134LLBZ','pull',package_path[len('package:'):],str(OUT/'installed.apk'))
    write(OUT/'manifest.json',dict(source=manifest,apk=sha((OUT/'installed.apk').read_bytes()),
        workflowPrefs=sha(json.dumps(values,sort_keys=True,ensure_ascii=False).encode()),
        reverse=adb('R5CW134LLBZ','reverse','--list').splitlines(),
        credentialFilesCopied=False,phone='R5CW134LLBZ',gitState='user untracked files preserved'))
    print('Baseline protected: sources='+str(len(manifest))+'; installed APK and workflow state; no credentials.')

if __name__=='__main__':freeze()
