"""Verify final devices and assemble relocatable audit tools; no skill writes."""
import json
import shutil
import subprocess
import sys
from pathlib import Path
from transfer_run import approved
from workflow_experiment import ROOT,adb,write
from migration_matrix import display
from recovery_matrix import source_closure,installed_hash
from workflow_capture import PROBE,APP

root=ROOT/'evaluation/user-robustness'
skill=json.loads((ROOT/'evaluation/user-recording-100/saved-skill.json').read_text(encoding='utf-8'))
before=json.loads((root/'phone-before/device.json').read_text(encoding='utf-8'))
verified={}
for serial,label in [('R5CW134LLBZ','phone'),('emulator-5554','emulator')]:
    assert approved(serial)==skill
    packages={p:installed_hash(serial,p)[1] for p in (PROBE,APP,'edu.sydney.evaluation')}
    assert all(packages[p]==before['packages'][p]['sha256'] for p in packages)
    original=json.loads((root/(label+'-before')/'device.json').read_text(encoding='utf-8'))['display']
    assert display(serial)==original
    verified[label]=dict(approvedSkillUnchanged=True,displayRestored=True,packages=packages)
write(root/'final-device-check.json',verified)
source=ROOT/'model-gateway';dest=root/'replay-tools';dest.mkdir(exist_ok=False)
for name in source_closure(source,['user_robustness_audit.py']):shutil.copy2(source/name,dest/name)
evidence=root/'source-skill';evidence.mkdir(exist_ok=False)
for name in ('saved-skill.json','original-trace.json','confirmed-trace.json','provenance.json'):
    shutil.copy2(ROOT/'evaluation/user-recording-100'/name,evidence/name)
reports={}
for group in ('phone-normal','phone-challenge','emulator-display'):
    subprocess.run([sys.executable,str(dest/'user_robustness_audit.py'),str(root/group)],check=True,stdout=subprocess.DEVNULL)
    reports[group]=json.loads((root/group/'reaudit.json').read_text(encoding='utf-8'))
write(root/'combined-audit.json',{k:{f:v for f,v in report.items() if f!='rows'} for k,report in reports.items()})
print('Device versions/displays/skills verified; portable offline audit rerun for all groups.')
