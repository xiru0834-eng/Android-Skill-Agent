"""Controlled UI demonstration. Source is AUTOMATED, never evidence of a human gesture."""
import argparse
import base64
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from workflow_experiment import adb, write
from workflow_contract import compile_evidence
from transfer_input_ready import wait_input_ready

PROBE='edu.sydney.probe'; APP='edu.sydney.transferlab'

def tree(serial,timeout=40):
    text=adb(serial,'shell','am','instrument','-w','edu.sydney.evaluation/.Observer',timeout=timeout)
    match=re.search(r'INSTRUMENTATION_RESULT: xml=(\S+)',text)
    if not match:raise RuntimeError('No allowed UI evidence')
    return ET.fromstring(base64.b64decode(match[1]))

def click(serial,key,package=PROBE):
    began=time.monotonic()
    for attempt in range(5):
        ui=tree(serial);nodes=[n for n in ui.iter('node') if n.get('resource-id')==package+':id/'+key]
        if not nodes and package==PROBE and attempt==0:
            advanced=[n for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/homeAdvanced']
            if len(advanced)==1:
                b=list(map(int,re.findall(r'-?\d+',advanced[0].get('bounds',''))))
                if len(b)==4 and b[2]>b[0] and b[3]>b[1]:
                    adb(serial,'shell','input','tap',(b[0]+b[2])//2,(b[1]+b[3])//2);time.sleep(.3);continue
        if len(nodes)!=1 or nodes[0].get('enabled')!='true':raise RuntimeError('Missing or ambiguous UI: '+key)
        bounds=list(map(int,re.findall(r'-?\d+',nodes[0].get('bounds',''))))
        if len(bounds)==4 and bounds[2]>bounds[0] and bounds[3]>bounds[1]:break
        # This is only normal scrolling of the controller's buttons, not a
        # hidden scrolling capability added to the skill's target executor.
        panels=[n for n in ui.iter('node') if n.get('class')=='android.widget.ScrollView']
        if package!=PROBE or len(panels)!=1 or attempt==4:raise RuntimeError('Invalid bounds')
        b=list(map(int,re.findall(r'-?\d+',panels[0].get('bounds',''))))
        if len(b)!=4 or b[2]<=b[0] or b[3]<=b[1]:raise RuntimeError('Invalid scroll container')
        adb(serial,'shell','input','swipe',(b[0]+b[2])//2,int(b[1]+.8*(b[3]-b[1])),(b[0]+b[2])//2,int(b[1]+.3*(b[3]-b[1])),250)
        time.sleep(.3)
    readiness=None
    if serial=='emulator-5554' and package==PROBE and key in ('flowEntry','flowRun'):
        activity=PROBE+'/'+PROBE+('.MainActivity' if key=='flowEntry' else '.WorkflowActivity')
        readiness=wait_input_ready(lambda:adb(serial,'shell','dumpsys','input',timeout=3),activity,
            (bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2)
    submitted=time.monotonic()
    adb(serial,'shell','input','tap',(bounds[0]+bounds[2])//2,(bounds[1]+bounds[3])//2)
    returned=time.monotonic()
    time.sleep(.65)
    return dict(key=key,package=package,bounds=bounds,operatorStartedMs=round(began*1000),
                inputCommandStartedMs=round(submitted*1000),inputCommandReturnedMs=round(returned*1000),
                preparationMs=round((submitted-began)*1000),inputCommandMs=round((returned-submitted)*1000),inputReadiness=readiness)

def workbench(serial):
    adb(serial,'shell','am','start','-n',PROBE+'/.MainActivity','-f','0x04000000');time.sleep(.5)
    entry=click(serial,'flowEntry')
    time.sleep(1.0)  # Let the Activity transition settle before using its final bounds.
    return entry

def main():
    p=argparse.ArgumentParser();p.add_argument('--device',choices=['R5CW134LLBZ','emulator-5554'],required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--allow-experiment',action='store_true');args=p.parse_args()
    if not args.allow_experiment:p.error('Explicit experimental capture required')
    args.output.mkdir(parents=True,exist_ok=False);serial=args.device
    write(args.output/'protocol.json',dict(source='AUTOMATED',device=serial,modelCalls=0,approval=False))
    adb(serial,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','layout','multi','--es','fault','normal','--es','initial','0,40,0,3');time.sleep(.5)
    try:
        workbench(serial);click(serial,'flowRecordTest');time.sleep(1)
        for key in ('wfOpenLamp','wfLampPower','wfLampValue60','wfLampSave','wfOpenFan','wfFanPower','wfFanValue1','wfFanSave'):
            click(serial,key,APP)
        workbench(serial);click(serial,'flowStop')
        trace=json.loads(adb(serial,'shell','run-as',PROBE,'cat','files/workflow-trace.json'))
        write(args.output/'trace.json',trace)
        skill=compile_evidence(trace);write(args.output/'evidence-candidate.json',skill)
        write(args.output/'result.json',dict(status='CAPTURED',steps=len(trace['steps']),source=trace['source']))
        print('CAPTURED AUTOMATED; evidence validates; no approval or model call')
    except Exception as e:
        write(args.output/'failure.json',dict(error=type(e).__name__,reason=str(e)))
        try:write(args.output/'trace.json',json.loads(adb(serial,'shell','run-as',PROBE,'cat','files/workflow-trace.json')))
        except Exception:pass
        raise
    finally:
        try:workbench(serial);click(serial,'flowStop')
        except Exception:pass

if __name__=='__main__':main()
