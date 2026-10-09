"""Named-workflow test operator: normal UI only, no approval or private preference writes."""
import argparse
import base64
import json
import re
import secrets
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from workflow_experiment import adb,write,ADB,ROOT
from workflow_capture import tree,PROBE,APP
from transfer_run import approved,private,audited
from workflow_contract import compile_evidence
from transfer_input_ready import wait_input_ready

def prefs(serial,name='recorded_workflows'):
    raw=adb(serial,'shell','run-as',PROBE,'cat','shared_prefs/'+name+'.xml')
    return {n.get('name'):n.text if n.tag=='string' else n.get('value') for n in ET.fromstring(raw)}

def snap(serial,path):
    path.parent.mkdir(parents=True,exist_ok=True)
    p=subprocess.run([str(ADB),'-s',serial,'exec-out','screencap','-p'],capture_output=True,check=True);path.write_bytes(p.stdout)
    path.with_suffix('.xml').write_text(ET.tostring(tree(serial),encoding='unicode'),encoding='utf-8')

def scroll_points(target,panel):
    x=(panel[0]+panel[2])//2;low=int(panel[1]+.65*(panel[3]-panel[1]));high=int(panel[1]+.40*(panel[3]-panel[1]))
    return (x,high,x,low) if target is not None and target[3]<=panel[1] else (x,low,x,high)

def node(serial,key,package=PROBE):
    for attempt in range(33):
        ui=tree(serial);found=[n for n in ui.iter('node') if n.get('resource-id')==package+':id/'+key]
        if len(found)>1:raise RuntimeError('Ambiguous control '+key)
        target=None
        if found:
            b=list(map(int,re.findall(r'-?\d+',found[0].get('bounds',''))))
            target=b if len(b)==4 else None
            if len(b)==4 and b[2]>b[0] and b[3]>b[1] and found[0].get('enabled')=='true':return found[0]
        panels=[n for n in ui.iter('node') if n.get('class')=='android.widget.ScrollView']
        if package!=PROBE or len(panels)!=1:raise RuntimeError('Unavailable control '+key)
        if attempt==32:break
        b=list(map(int,re.findall(r'-?\d+',panels[0].get('bounds',''))))
        adb(serial,'shell','input','swipe',*scroll_points(target,b),650);time.sleep(.25)
    raise RuntimeError('Control not reachable '+key)

def tap(serial,key,package=PROBE):
    n=node(serial,key,package);time.sleep(.5)
    n=node(serial,key,package);b=list(map(int,re.findall(r'-?\d+',n.get('bounds',''))))
    adb(serial,'shell','input','tap',(b[0]+b[2])//2,(b[1]+b[3])//2);time.sleep(.7)

def text(serial,key,value):
    node(serial,key)
    encoded=base64.b64encode(value.encode()).decode()
    payload=['-e','clearText','true'] if value=='' else ['-e','value',encoded]
    result=adb(serial,'shell','am','instrument','-w','-e','field',key,*payload,'edu.sydney.evaluation/.LanguageInput')
    if 'PASS UI text set' not in result:raise RuntimeError('Text input failed '+key)

def home(serial):
    adb(serial,'shell','am','start','-W','-n',PROBE+'/.MainActivity','-f','0x04000000');time.sleep(.5)

def library(serial):
    home(serial);tap(serial,'namedLibrary')
    if serial=='emulator-5554':
        # This is test preparation, not an executor retry or a longer deadline.
        # Reuse the known-format InputDispatcher guard; a visible old tree alone
        # does not prove the new Activity can consume text or pointer input.
        wait_input_ready(lambda:adb(serial,'shell','dumpsys','input',timeout=3),
                         PROBE+'/'+PROBE+'.WorkflowLibraryActivity',100,100)

def wait_fixture(read,case,initial,clock=time.monotonic,sleep=time.sleep,timeout=8):
    end=clock()+timeout
    while clock()<end:
        before=read()
        if before.get('caseId')==case and before.get('initial')==initial:return before
        sleep(.2)
    raise RuntimeError('Fixture reset not confirmed; task not started')

def fixture(serial,initial):
    case=secrets.token_hex(8)
    adb(serial,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','caseId',case,'--es','layout','multi','--es','fault','normal','--es','initial',','.join(map(str,initial)))
    return wait_fixture(lambda:private(serial,APP,'workflow-oracle.json'),case,initial)

DEMONSTRATIONS={
    'reading':dict(name='阅读60 / Reading60',goal='Turn on the reading lamp at 60% and turn on the fan at low speed.',target=[1,60,1,1],initial=[0,40,0,3]),
    'bright':dict(name='明亮80 / Bright80',goal='Turn on the reading lamp at 80% and turn on the fan at high speed.',target=[1,80,1,3],initial=[0,40,0,1])}

def capture(serial,which,out):
    case=DEMONSTRATIONS[which];out.mkdir(parents=True,exist_ok=False)
    write(out/'protocol.json',dict(case,source='AUTOMATED',normalGuidedUI=True))
    old=approved(serial);write(out/'approval-before.json',old)
    before=fixture(serial,case['initial']);write(out/'before.json',before)
    home(serial);tap(serial,'homeAdvanced');tap(serial,'guidedTest')
    if prefs(serial,'teaching_journey').get('currentTrace'):
        tap(serial,'teachNew')
    text(serial,'teachName',case['name']);text(serial,'teachGoal',case['goal'])
    tap(serial,'teachRecord');tap(serial,'button1','android');time.sleep(1)
    for key in ['wfOpenLamp','wfLampPower','wfLampValue'+str(case['target'][1]),'wfLampSave','wfOpenFan','wfFanPower','wfFanValue'+str(case['target'][3]),'wfFanSave']:
        tap(serial,key,APP)
    home(serial);tap(serial,'teachEntry');tap(serial,'teachStop')
    trace=private(serial,PROBE,'workflow-trace.json');write(out/'trace.json',trace)
    candidate=compile_evidence(trace);write(out/'local-candidate.json',candidate)
    assert trace['source']=='AUTOMATED' and candidate['finalGoals']==case['target'] and approved(serial)==old
    oracle=audited(serial);write(out/'oracle.json',oracle)
    assert oracle['oracle']['caseId']==before['caseId'] and oracle['oracle']['events'][-1]['saved']==case['target']
    snap(serial,out/'record-preview.png');print('CAPTURED '+which+'; eight observed steps; approval unchanged',flush=True)

def generate_save(serial,which,out):
    case=DEMONSTRATIONS[which];trace=json.loads((out/'trace.json').read_text(encoding='utf-8'))
    assert private(serial,PROBE,'workflow-trace.json')==trace
    tap(serial,'teachGenerate')
    for _ in range(55):
        state=prefs(serial,'teaching_journey')
        if state.get('draft') and state.get('draftTrace'):
            assert json.loads(state['draftTrace'])==trace;break
        time.sleep(1)
    else:raise RuntimeError('No compiled draft; capture kept')
    candidate=json.loads(state['draft']);assert candidate==compile_evidence(trace)
    write(out/'model-candidate.json',candidate);snap(serial,out/'guide-preview.png')
    tap(serial,'teachSave');snap(serial,out/'save-confirmation.png');tap(serial,'button1','android')
    saved=prefs(serial);assert json.loads(saved['approved'])==candidate
    entries=json.loads(saved['library']);assert any(e['name']==case['name'] and e['skill']==candidate for e in entries)
    write(out/'saved-skill.json',candidate);write(out/'library-after.json',entries)
    snap(serial,out/'saved.png');print('SAVED '+which+' via normal guide approval',flush=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['preserve','capture','save','screen']);p.add_argument('--which',choices=list(DEMONSTRATIONS),default='reading')
    p.add_argument('--device',choices=['R5CW134LLBZ','emulator-5554'],default='R5CW134LLBZ');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='capture':
        try:capture(a.device,a.which,a.output)
        except Exception as e:
            write(a.output/'failure.json',dict(error=type(e).__name__,reason=str(e)));snap(a.device,a.output/'failure.png');raise
    elif a.mode=='save':generate_save(a.device,a.which,a.output)
    else:
        a.output.mkdir(parents=True,exist_ok=False)
        if a.mode=='preserve':
            write(a.output/'workflow-before.json',prefs(a.device));write(a.output/'trace-before.json',private(a.device,PROBE,'workflow-trace.json'))
            write(a.output/'teaching-before.json',prefs(a.device,'teaching_journey'));print('Scoped state preserved; no credentials copied')
        else:library(a.device);snap(a.device,a.output/'library.png')

if __name__=='__main__':main()
