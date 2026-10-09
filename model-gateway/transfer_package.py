"""Whitelist-only research delivery; never packages settings or credentials."""
import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from workflow_experiment import write


def main():
    p=argparse.ArgumentParser();p.add_argument('--freeze',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--tables',type=Path,required=True)
    p.add_argument('batches',type=Path,nargs='+');a=p.parse_args()
    manifest=json.loads((a.freeze/'manifest.json').read_text(encoding='utf-8'));files=manifest['sourceFiles']
    sources={}
    for prefix,name in [('android-agent-probe/','demo-probe.apk'),('android-transfer-bench/','transfer-bench.apk')]:
        matches=[key for key in files if key.startswith(prefix) and key.endswith('.apk')]
        if len(matches)!=1:raise ValueError('APK ambiguity')
        key=matches[0];source=a.freeze/'files'/key
        if hashlib.sha256(source.read_bytes()).hexdigest()!=files[key]:raise ValueError('APK changed')
        sources[name]=source
    for suffix,name in [('/teach-once-v2.json','teach-once-skill.json'),('/trace.json','teaching-trace.json')]:
        matches=[key for key in files if key.endswith(suffix)]
        if len(matches)!=1:raise ValueError('Teaching artifact ambiguity')
        key=matches[0];source=a.freeze/'files'/key
        if hashlib.sha256(source.read_bytes()).hexdigest()!=files[key]:raise ValueError('Teaching artifact changed')
        sources[name]=source
    sources.update({'README.md':Path('output/teach-once-delivery-readme.md'),'results.md':Path('output/teach-once-transfer-results.md'),
        'trials.csv':a.report/'trials.csv','tables-and-failures.md':a.tables/'tables-and-failures.md',
        'evidence-summary.json':a.tables/'evidence-summary.json'})
    sources.update({'experiment-plan.md':Path('tasks/workflow-budget-v3-plan.md'),
        'evidence/environment-stop.json':Path('evaluation/teach-once/environment-stop.json'),
        'evidence/timing-v3.json':Path('evaluation/teach-once/final-timing-v3.json'),
        'evidence/system-anr.png':Path('evaluation/teach-once/core-v3-anr-parser-guard/system-anr.png'),
        'evidence/input-transitions.txt':Path('evaluation/teach-once/core-v3-input-diagnosis/input-transitions.txt')})
    for batch in a.batches:
        # Preserve the relative nested display label without flattening collisions.
        relative=batch.relative_to(Path('evaluation/teach-once'))
        for name in ('protocol.json','skill.json','results.json','reaudit.json','summary.json','restored.json'):
            if (batch/name).is_file():sources[str(Path('evidence')/relative/name)]=batch/name
        for run in sorted(batch.glob('run-*')):
            for name in ('case.json','before.json','operator-start.json','terminal.json','oracle.json','audit.json','persisted.json','journal.json','score.json','failure.json'):
                if (run/name).is_file():sources[str(Path('evidence')/relative/run.name/name)]=run/name
    if any(not f.is_file() for f in sources.values()):raise ValueError('Incomplete delivery sources')
    archive=a.output.with_suffix('.zip')
    if a.output.exists() or archive.exists():raise ValueError('Refuse overwrite')
    a.output.mkdir(parents=True)
    hashes={}
    for name,source in sources.items():
        target=a.output/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
        hashes[Path(name).as_posix()]=hashlib.sha256(target.read_bytes()).hexdigest()
    write(a.output/'SHA256SUMS.json',hashes)
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for f in sorted(a.output.rglob('*')):
            if f.is_file():z.write(f,str(f.relative_to(a.output)))
    print(json.dumps(dict(files=len(hashes),archive=str(archive),archiveSha256=hashlib.sha256(archive.read_bytes()).hexdigest())))


if __name__=='__main__':main()
