"""Bounded user-journey checks. No private approval writes; only normal review buttons."""
import argparse
import base64
import json
import re
import subprocess
import time
import secrets
import xml.etree.ElementTree as ET
from pathlib import Path
from workflow_experiment import adb, write, ADB
from workflow_capture import tree, click, PROBE, APP

SERIAL='R5CW134LLBZ'

def preferences(name):
    raw=adb(SERIAL,'shell','run-as',PROBE,'cat','shared_prefs/'+name+'.xml')
    return {n.get('name'): n.text if n.tag=='string' else n.get('value') for n in ET.fromstring(raw)}

def screen(library=False):
    adb(SERIAL,'shell','am','start','-n',PROBE+'/.MainActivity','-f','0x04000000')
    time.sleep(.8); click(SERIAL,'teachLibrary' if library else 'teachEntry');time.sleep(.5)

def find_visible(key):
    # Control-panel scrolling is a user interaction, not a target executor capability.
    for attempt in range(15):
        ui=tree(SERIAL)
        nodes=[n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/'+key]
        if len(nodes)==1:
            bounds=list(map(int,re.findall(r'-?\d+',nodes[0].get('bounds',''))))
            if len(bounds)==4 and bounds[2]>bounds[0] and bounds[3]>bounds[1]:return nodes[0]
        panels=[n for n in ui.iter('node') if n.get('class')=='android.widget.ScrollView']
        if len(panels)!=1:raise RuntimeError('No scroll container')
        b=list(map(int,re.findall(r'-?\d+',panels[0].get('bounds',''))))
        adb(SERIAL,'shell','input','swipe',(b[0]+b[2])//2,int(b[1]+.8*(b[3]-b[1])),int((b[0]+b[2])//2),int(b[1]+.3*(b[3]-b[1])),250)
        time.sleep(.3)
    raise RuntimeError('User control unavailable: '+key)

def tap(key):
    node=find_visible(key)
    # Scrolling/Activity transitions can publish final-looking bounds before input settles.
    # Re-read after settling, then issue exactly one click (never retry a save/execute).
    time.sleep(1)
    node=find_visible(key)
    if node.get('enabled')!='true':raise RuntimeError('Control disabled: '+key)
    b=list(map(int,re.findall(r'-?\d+',node.get('bounds',''))))
    adb(SERIAL,'shell','input','tap',(b[0]+b[2])//2,(b[1]+b[3])//2);time.sleep(.7)

def screenshot(path):
    p=subprocess.run([str(ADB),'-s',SERIAL,'exec-out','screencap','-p'],capture_output=True,check=True)
    path.write_bytes(p.stdout)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['preserve','open','cancel','compile','save','run','stop-run','language','record-new-ui'])
    parser.add_argument('--initial',default=None)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    if args.mode=='record-new-ui':
        adb(SERIAL,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','layout','multi','--es','fault','normal','--es','initial','0,40,0,3','--es','caseId',secrets.token_hex(8))
    if args.mode=='preserve':
        write(args.output/'workflow-before.json',preferences('recorded_workflows'))
        write(args.output/'trace-before.json',json.loads(adb(SERIAL,'shell','run-as',PROBE,'cat','files/workflow-trace.json')))
        return
    if args.mode in ('run','stop-run'):
        initial=[int(n) for n in (args.initial or '0,40,0,3').split(',')];nonce=secrets.token_hex(8)
        adb(SERIAL,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','layout','multi','--es','fault','normal','--es','initial',','.join(map(str,initial)),'--es','caseId',nonce)
        before=json.loads(adb(SERIAL,'shell','run-as',APP,'cat','files/workflow-oracle.json'))
        assert before['caseId']==nonce and before['initial']==initial
        write(args.output/'before.json',before)
        previous=json.loads(preferences('recorded_workflows')['result']).get('runId')
    screen(library=args.mode in ('run','stop-run'))
    if args.mode=='language':
        before=preferences('recorded_workflows').get('approved')
        tap('teachLanguage');screenshot(args.output/'teaching-english.png')
        assert any(n.get('text')=='Teach a workflow' for n in tree(SERIAL).iter('node'))
        tap('teachLanguage');assert preferences('recorded_workflows').get('approved')==before
        write(args.output/'language.json',dict(passed=True,approvalUnchanged=True));return
    if args.mode=='open':screenshot(args.output/'teaching-start.png');return
    if args.mode in ('cancel','record-new-ui'):
        before=preferences('recorded_workflows').get('approved')
        tap('teachRecord');click(SERIAL,'button1','android');time.sleep(1)
        if args.mode=='record-new-ui':
            for key in ('wfOpenLamp','wfLampPower','wfLampValue60','wfLampSave','wfOpenFan','wfFanPower','wfFanValue1','wfFanSave'):
                click(SERIAL,key,APP)
        screenshot(args.output/'recording-controls.png')
        observed=adb(SERIAL,'shell','am','instrument','-w','-e','probeOverlay','true','edu.sydney.evaluation/.Observer')
        overlay_tree=ET.fromstring(base64.b64decode(re.search(r'INSTRUMENTATION_RESULT: xml=(\S+)',observed)[1]))
        labels=('结束示范','Finish teaching') if args.mode=='record-new-ui' else ('取消录制','Cancel')
        nodes=[n for n in overlay_tree.iter('node') if n.get('text') in labels and n.get('class')=='android.widget.Button']
        if len(nodes)!=1:raise RuntimeError('Recording cancel not reachable')
        b=list(map(int,re.findall(r'\d+',nodes[0].get('bounds'))))
        adb(SERIAL,'shell','input','tap',(b[0]+b[2])//2,(b[1]+b[3])//2);time.sleep(1)
        trace=json.loads(adb(SERIAL,'shell','run-as',PROBE,'cat','files/workflow-trace.json'))
        assert trace['end']==('STOPPED' if args.mode=='record-new-ui' else 'CANCELLED')
        assert preferences('recorded_workflows').get('approved')==before
        if args.mode=='record-new-ui':
            from workflow_contract import compile_evidence
            skill=compile_evidence(trace)
            write(args.output/'record.json',dict(passed=True,actualDemonstrator='AUTOMATED_UI_TEST',
                warning='HUMAN_DECLARED is the UI button declaration, not proof of a human finger',trace=trace,skill=skill))
            return
        tap('teachGenerate');assert 'draft' not in preferences('teaching_journey')
        screenshot(args.output/'cancelled-recording.png');write(args.output/'cancel.json',dict(passed=True,approvedUnchanged=True,trace=trace));return
    if args.mode=='compile':
        before=preferences('recorded_workflows').get('approved')
        tap('teachGenerate');began=time.monotonic()
        while time.monotonic()-began<55:
            prefs=preferences('teaching_journey')
            if prefs.get('draft'):break
            time.sleep(.5)
        else:raise RuntimeError('No draft; inspect visible error, do not infer success')
        assert preferences('recorded_workflows').get('approved')==before
        write(args.output/'generated-draft.json',json.loads(prefs['draft']))
        write(args.output/'compile.json',dict(passed=True,seconds=time.monotonic()-began,approvalUnchanged=True))
        screenshot(args.output/'generated-guide.png');return
    if args.mode=='save':
        tap('teachSave');screenshot(args.output/'review-dialog.png');click(SERIAL,'button1','android')
        state=preferences('recorded_workflows');draft=preferences('teaching_journey')['draft']
        assert json.loads(state['approved'])==json.loads(draft)
        write(args.output/'saved.json',dict(passed=True,name=state['name'],skill=json.loads(draft),source='AUTOMATED_UI_REVIEW'))
        return
    if args.mode in ('run','stop-run'):
        tap('teachRun');click(SERIAL,'button1','android')
        if args.mode=='stop-run':
            observed=adb(SERIAL,'shell','am','instrument','-w','-e','probeOverlay','true','edu.sydney.evaluation/.Observer')
            controls=ET.fromstring(base64.b64decode(re.search(r'INSTRUMENTATION_RESULT: xml=(\S+)',observed)[1]))
            nodes=[n for n in controls.iter('node') if n.get('text') in ('停止并返回','Stop / return')]
            assert len(nodes)==1,'Stop not available during execution'
            b=list(map(int,re.findall(r'\d+',nodes[0].get('bounds'))))
            adb(SERIAL,'shell','input','tap',(b[0]+b[2])//2,(b[1]+b[3])//2)
        time.sleep(.3)
        for _ in range(70):
            result=json.loads(preferences('recorded_workflows')['result'])
            if result['status']!='RUNNING':break
            time.sleep(.5)
        assert result['runId']!=previous
        write(args.output/'run.json',result);screenshot(args.output/'run-finished.png')
        oracle=json.loads(adb(SERIAL,'shell','run-as',APP,'cat','files/workflow-oracle.json'));write(args.output/'oracle.json',oracle)
        time.sleep(1)
        after=json.loads(adb(SERIAL,'shell','run-as',APP,'cat','files/workflow-oracle.json'));write(args.output/'after-1s.json',after)
        assert oracle==after and oracle['caseId']==nonce,'Late action or fixture changed'
        assert result['status']==('CANCELLED' if args.mode=='stop-run' else 'SUCCEEDED'),result['reason']
        if args.mode=='run':
            assert oracle['events'][-1]['saved']==result['goal']==[1,60,1,1]
            assert oracle['events'][-1]['draft']==result['goal']
        write(args.output/'verified.json',dict(passed=True,mode=args.mode,elapsedMs=result['finishedMs']-result['startedMs'],inputs=len(result['actions'])))

if __name__=='__main__':main()
