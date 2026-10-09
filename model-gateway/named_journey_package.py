"""Seal complete named-journey evidence without credentials; refuse overwrite."""
import hashlib
import json
import re
import shutil
import zipfile
from pathlib import Path
from workflow_experiment import write

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    source=Path('evaluation/named-journey');summary=json.loads((source/'summary.json').read_text(encoding='utf-8'))
    assert all(summary[n]['n']==12 for n in ['phone-confirmation','emulator-confirmation'])
    root=Path('output/named-skill-delivery');archive=root.with_suffix('.zip')
    if root.exists() or archive.exists():raise RuntimeError('Refuse overwriting a delivery')
    files={str(Path('evidence')/p.relative_to(source)):p for p in source.rglob('*') if p.is_file()}
    files.update({'README.md':Path('output/named-skill-user-guide.md'),'results.md':Path('output/named-skill-journey-results.md'),
        'design.md':Path('tasks/named-skill-journey-design.md'),
        'demo-probe-v23.apk':Path('android-agent-probe/build/manual/demo-probe-named-dev.apk'),
        'transfer-bench-v6.apk':source/'implementation-snapshot/installed/R5CW134LLBZ/edu.sydney.transferlab.apk'})
    for p in Path('model-gateway').glob('named_*.py'):files[str(Path('final-analysis-source')/p.name)]=p
    for name,p in files.items():
        if not p.is_file():raise RuntimeError('Missing '+name)
        if p.suffix in ['.json','.xml','.txt','.md','.py','.java']:
            data=p.read_bytes()
            if re.search(rb'(?:sk-proj-|sk-ws-|apikey_)[A-Za-z0-9._-]{20,}|Bearer [a-f0-9]{32,}',data):raise RuntimeError('Possible secret; do not package '+name)
    root.mkdir();hashes={}
    for name,p in files.items():
        dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest);hashes[Path(name).as_posix()]=sha(dest)
    write(root/'SHA256SUMS.json',hashes)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(root).as_posix())
    write(Path('output/named-skill-delivery-integrity.json'),dict(files=len(hashes),archive=archive.as_posix(),sha256=sha(archive),bytes=archive.stat().st_size))
    print('SEALED '+str(len(hashes))+' files; archive '+str(archive),flush=True)

if __name__=='__main__':main()
