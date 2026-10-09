"""Freeze the exact experimental artifacts; never includes credentials or preferences."""
import hashlib
import argparse
import json
import shutil
from pathlib import Path
from workflow_experiment import write,adb
from workflow_contract import canonical,compile_evidence
from transfer_run import approved

def main():
    p=argparse.ArgumentParser();p.add_argument('--version',type=int,choices=[1,2,3],default=1);version=p.parse_args().version
    out=Path(f'evaluation/teach-once/freeze-v{version}');out.mkdir(exist_ok=False)
    teaching=Path(f'evaluation/teach-once/source-teaching-dev-v{min(version,2)}/trace.json')
    exported=Path('evaluation/teach-once/exported-source-dev-v1.json') if version==1 else Path('evaluation/teach-once/source-review-v2/teach-once-v2.json')
    skill=json.loads(exported.read_text(encoding='utf-8'));trace=json.loads(teaching.read_text(encoding='utf-8'))
    assert compile_evidence(trace)==skill
    assert approved('R5CW134LLBZ')==skill==approved('emulator-5554')
    sources=[]
    for folder in ['android-agent-probe/app/src/main','android-transfer-bench/app/src/main','evaluation/android-observer/app/src/main']:
        sources.extend(p for p in Path(folder).rglob('*') if p.is_file())
    for name in ['transfer_run.py','transfer_cases.py','transfer_audit.py','transfer_reaudit.py','transfer_report.py','transfer_display.py','workflow_review_export.py','workflow_score.py','workflow_capture.py','workflow_import.py','workflow_contract.py','workflow_compile.py','test_transfer_audit.py']:
        sources.append(Path('model-gateway')/name)
    if version==3:
        sources.extend(Path('model-gateway')/name for name in ['transfer_requests.py','test_transfer_requests.py','transfer_terminal_wait.py','transfer_protection.py','transfer_evidence_report.py','transfer_freeze.py','transfer_resume.py','test_transfer_resume.py','transfer_integrity.py','transfer_screenshot.py','workflow_experiment.py'])
        sources.extend([Path('tasks/workflow-budget-v3-plan.md'),Path('tasks/transfer-harness-timing-amendment.md'),Path('android-agent-probe/tests/edu/sydney/probe/WorkflowTimingTest.java')])
    sources.extend([Path('tasks/teach-once-transfer-protocol.md'),Path('tasks/teach-once-execution-log.md'),
        Path('android-agent-probe/build/manual/'+{1:'demo-probe-audit-v11.apk',2:'demo-probe-audit-v12.apk',3:'demo-probe-audit-v13.apk'}[version]),
        Path('android-transfer-bench/build/manual/'+('transfer-bench-audit-dev.apk' if version==1 else 'transfer-bench-audit-v6.apk')),teaching,exported,
        Path(f'evaluation/teach-once/compile-dev-v{min(version,2)}/audit.json'),
        Path('evaluation/teach-once/source-review-dialog.json' if version==1 else 'evaluation/teach-once/source-review-v2/review-dialog.json'),
        Path('evaluation/teach-once/target-review-dialog.json' if version==1 else 'evaluation/teach-once/target-review-v2/review-dialog.json')])
    hashes={}
    for p in sources:
        target=out/'files'/p;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
        hashes[p.as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
    devices={}
    for serial in ['R5CW134LLBZ','emulator-5554']:
        devices[serial]=dict(size=adb(serial,'shell','wm','size'),density=adb(serial,'shell','wm','density'),
            sdk=adb(serial,'shell','getprop','ro.build.version.sdk'),service=adb(serial,'shell','dumpsys','accessibility'))
    write(out/'manifest.json',dict(source='AUTOMATED',teachingPackages=1,teachingFirstAttemptRate='NOT_ESTIMATED',
        skillSemanticSha256=hashlib.sha256(canonical(skill).encode()).hexdigest(),sourceFiles=hashes,devices=devices,
        note='One development demonstration frozen for repeated execution confirmation; no claim of human demonstration.'))
    print('FROZEN source trace -> exported file -> both device approvals match; files='+str(len(hashes)))

if __name__=='__main__':main()
