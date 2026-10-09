"""Preserve this release, including failed setup attempts, without secrets."""
import hashlib,json,re,shutil,zipfile
from pathlib import Path
from workflow_experiment import write

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    source=Path('evaluation/partial-workflow');summary=json.loads((source/'summary.json').read_text(encoding='utf-8'))
    if any(summary[n]['n']!=12 for n in ['phone-matrix','emulator-reference','emulator-compact-final']):raise RuntimeError('Incomplete confirmation')
    root=Path('output/partial-skill-delivery');archive=root.with_suffix('.zip')
    if root.exists() or archive.exists():raise RuntimeError('Refuse overwriting delivery')
    files={str(Path('evidence')/p.relative_to(source)):p for p in source.rglob('*') if p.is_file()}
    files.update({'README.md':Path('output/单设备技能_怎么使用.md'),'results.md':Path('output/partial-workflow-results.md'),
        'design.md':Path('tasks/partial-workflow-design.md'),'review.md':Path('output/partial-workflow-code-review.md'),
        'demo-probe-v24.apk':Path('android-agent-probe/build/manual/demo-probe-partial-dev.apk'),
        'transfer-bench-v6.apk':source/'implementation-snapshot/installed/R5CW134LLBZ/edu.sydney.transferlab.apk'})
    for p in Path('model-gateway').glob('*.py'):files[str(Path('final-analysis-source')/p.name)]=p
    for p in Path('android-agent-probe/tests').rglob('*.java'):files[str(Path('final-java-tests')/p.name)]=p
    for name,p in files.items():
        if p.suffix in ['.json','.xml','.txt','.md','.py','.java'] and re.search(rb'(?:sk-(?:proj-|ws-)?|apikey_)[A-Za-z0-9._-]{24,}|Bearer [a-f0-9]{32,}',p.read_bytes()):raise RuntimeError('Possible secret: '+name)
    root.mkdir();hashes={}
    for name,p in files.items():
        dest=root/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest);hashes[Path(name).as_posix()]=sha(dest)
    write(root/'SHA256SUMS.json',hashes)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(root.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(root).as_posix())
    write(Path('output/partial-skill-delivery-integrity.json'),dict(files=len(hashes),archive=archive.as_posix(),sha256=sha(archive),bytes=archive.stat().st_size));print('SEALED '+str(len(hashes))+' files')

if __name__=='__main__':main()
