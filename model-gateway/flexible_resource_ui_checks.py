"""Normal phone resource dialog checks; never alters skills or credentials."""
import json
import time
from pathlib import Path
from named_journey_device import tap, tree, prefs, snap, home
from workflow_experiment import adb, write
from workflow_capture import PROBE

SERIAL='R5CW134LLBZ'
OUT=Path('output/flexible-workflow-v1/phone-final-preserved')

def enter(key,value):
    tap(SERIAL,key)
    adb(SERIAL,'shell','input','keyevent','123','67','67')
    adb(SERIAL,'shell','input','text',str(value))
    adb(SERIAL,'shell','input','keyevent','4')
    time.sleep(.3)
    fields=[n for n in tree(SERIAL).iter('node') if n.get('resource-id')==PROBE+':id/'+key]
    if len(fields)!=1 or fields[0].get('text')!=str(value):raise RuntimeError('Numeric UI input differs')

def main():
    original={name:prefs(SERIAL,name) for name in ('recorded_workflows','teaching_journey')}
    enter('teachRecordingMinutes',0);enter('teachConfirmationSeconds',1)
    tap(SERIAL,'button1','android')
    ui=tree(SERIAL)
    if not any(n.get('resource-id')==PROBE+':id/teachRecordingMinutes' for n in ui.iter('node')):
        raise RuntimeError('Invalid values incorrectly closed the dialog')
    snap(SERIAL,OUT/'budgets-invalid.png')
    enter('teachRecordingMinutes',2);enter('teachConfirmationSeconds',4)
    tap(SERIAL,'button1','android')
    ui=tree(SERIAL)
    if any(n.get('resource-id')==PROBE+':id/teachRecordingMinutes' for n in ui.iter('node')):
        raise RuntimeError('Valid values did not save')
    saved=prefs(SERIAL,'workflow_resources')
    if saved!={'recordingMinutes':'2','confirmationSeconds':'4'}:raise RuntimeError('Stored resource values differ')
    kept=all(prefs(SERIAL,name)==value for name,value in original.items())
    if not kept:raise RuntimeError('Unrelated workflow state changed')
    write(OUT/'resource-ui-checks.json',dict(invalidRejected=True,validSaved=True,otherWorkflowStatePreserved=kept,stored=saved,modelCalls=0))
    home(SERIAL);snap(SERIAL,OUT/'home-final.png')
    print('PASS phone resource dialog; invalid rejected, defaults saved, skills unchanged')

if __name__=='__main__':main()
