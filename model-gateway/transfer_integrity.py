"""Read-only provenance/deployment check for a frozen experiment package."""
import argparse
import hashlib
import json
import re
from pathlib import Path
from transfer_run import approved
from workflow_contract import canonical,compile_evidence
from workflow_experiment import adb,write


def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--freeze',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);manifest=load(a.freeze/'manifest.json');entries=manifest['sourceFiles'];frozen=a.freeze/'files'
    for name,expected in entries.items():
        if sha(frozen/name)!=expected:raise ValueError('Frozen file modified: '+name)
    current_changes=[name for name,expected in entries.items() if not Path(name).is_file() or sha(Path(name))!=expected]
    trace_name=next(k for k in entries if 'source-teaching-' in k and k.endswith('/trace.json'))
    export_name=next(k for k in entries if 'source-review-' in k and k.endswith('/teach-once-v2.json'))
    skill=load(frozen/export_name)
    if compile_evidence(load(frozen/trace_name))!=skill:raise ValueError('Teaching/export mismatch')
    semantic=hashlib.sha256(canonical(skill).encode()).hexdigest()
    if semantic!=manifest['skillSemanticSha256']:raise ValueError('Skill hash mismatch')
    devices={}
    for serial in ('R5CW134LLBZ','emulator-5554'):
        if approved(serial)!=skill:raise ValueError('Approval changed: '+serial)
        packages={}
        for package,project in (('edu.sydney.probe','android-agent-probe'),('edu.sydney.transferlab','android-transfer-bench')):
            remote=adb(serial,'shell','pm','path',package).strip()
            if not remote.startswith('package:/data/app/') or '\n' in remote:raise ValueError('Unexpected APK path')
            apk_name=next(k for k in entries if k.startswith(project+'/') and k.endswith('.apk'))
            installed=adb(serial,'shell','sha256sum',remote.removeprefix('package:')).split()[0]
            if not re.fullmatch('[0-9a-f]{64}',installed) or installed!=entries[apk_name]:raise ValueError('Installed APK changed: '+package)
            packages[package]=dict(sha256=installed,frozenArtifact=apk_name)
        devices[serial]=dict(approvalMatches=True,packages=packages,
            size=adb(serial,'shell','wm','size'),density=adb(serial,'shell','wm','density'))
    value=dict(frozenFilesVerified=len(entries),skillSemanticSha256=semantic,source='AUTOMATED',
               currentWorkspaceChanges=current_changes,devices=devices)
    write(a.output/'integrity.json',value)
    print(json.dumps(value,ensure_ascii=False))


if __name__=='__main__':main()
