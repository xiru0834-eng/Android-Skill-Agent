"""Restore the phone fixture, verify the saved skill, then show the user's guide."""
import hashlib
import json
from pathlib import Path
from transfer_run import run,approved
from workflow_experiment import ROOT,adb,write
from teaching_device_check import screen,tap,screenshot

out=ROOT/'evaluation/user-robustness/phone-handoff';out.mkdir(exist_ok=False)
skill=json.loads((ROOT/'evaluation/user-recording-100/saved-skill.json').read_text(encoding='utf-8'))
assert approved('R5CW134LLBZ')==skill
case=dict(initial=skill['finalGoals'],condition='handoff-already-at-target',fault='normal',repeat=0)
row=run('R5CW134LLBZ',case,out/'smoke',skill)
assert row['confirmed_success'] and row['inputs']==0
screen(library=True);tap('teachView');screenshot(out/'guide.png')
original=ROOT/'evaluation/user-recording-100/original-trace.json'
expected=json.loads((ROOT/'evaluation/user-recording-100/provenance.json').read_text(encoding='utf-8'))['originalSha256']
assert hashlib.sha256(original.read_bytes()).hexdigest()==expected
write(out/'handoff.json',dict(skillUnchanged=approved('R5CW134LLBZ')==skill,originalTraceUnchanged=True,
    faultCleared=True,actualGoal=skill['finalGoals'],additionalSmoke=row,excludedFrom70Cases=True))
print('Phone restored to normal; saved guide visible; approved skill unchanged.')
