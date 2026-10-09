"""Bounded UX checks on the allowed fixture. All demonstrations are AUTOMATED.

No API requests, review confirmations, or writes to approved skill preferences.
"""
import argparse
import base64
import hashlib
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from workflow_capture import APP, PROBE, click, workbench
from workflow_experiment import adb, ADB, write
from workflow_contract import compile_evidence
from recorder_regression import ROUTE

SERIAL='R5CW134LLBZ'
GUIDANCE=False
FAN_FIRST=False

def ui():
    raw=adb(SERIAL,'shell','am','instrument','-w','-e','probeOverlay','true','edu.sydney.evaluation/.Observer')
    match=re.search(r'INSTRUMENTATION_RESULT: xml=(\S+)',raw)
    if not match:raise RuntimeError('No scoped UI')
    return ET.fromstring(base64.b64decode(match[1]))

def node(root,key):
    matches=[n for n in root.iter('node') if n.get('resource-id')==PROBE+':id/'+key]
    if len(matches)!=1:raise AssertionError(('Not unique',key,len(matches)))
    return matches[0]

def press(key):
    n=node(ui(),key)
    assert n.get('enabled')=='true',(key,'disabled')
    b=list(map(int,re.findall(r'-?\d+',n.get('bounds',''))))
    assert len(b)==4 and b[2]>b[0] and b[3]>b[1],(key,b)
    adb(SERIAL,'shell','input','tap',(b[0]+b[2])//2,(b[1]+b[3])//2)
    time.sleep(.65)

def shot(folder,name):
    root=ui();(folder/(name+'.xml')).write_bytes(ET.tostring(root,encoding='utf-8'))
    (folder/(name+'.png')).write_bytes(subprocess.check_output([str(ADB),'-s',SERIAL,'exec-out','screencap','-p'],timeout=20))
    return root

def teaching():
    adb(SERIAL,'shell','am','start','-n',PROBE+'/.MainActivity','-f','0x04000000');time.sleep(.6)
    click(SERIAL,'teachEntry');time.sleep(.5)

def language(en):
    teaching()
    if (node(ui(),'teachLanguage').get('text')=='中文') != en:press('teachLanguage')

def read_trace():
    return json.loads(adb(SERIAL,'shell','run-as',PROBE,'cat','files/workflow-trace.json'))

def backup(out):
    (out/'recorded_workflows.xml').write_text(adb(SERIAL,'shell','run-as',PROBE,'cat','shared_prefs/recorded_workflows.xml'),encoding='utf-8')
    write(out/'trace.json',read_trace())
    remote=adb(SERIAL,'shell','pm','path',PROBE).strip().removeprefix('package:')
    adb(SERIAL,'pull',remote,str(out/'installed.apk'))
    write(out/'manifest.json',{'apkSha256':hashlib.sha256((out/'installed.apk').read_bytes()).hexdigest()})

def reset_fixture(fault='normal'):
    adb(SERIAL,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','layout','multi','--es','initial','0,40,0,3','--es','fault',fault);time.sleep(.5)

def run_case(out,case,en,repeat):
    folder=out/f'{case}-{"en" if en else "zh"}-{repeat}'
    folder.mkdir();language(en);workbench(SERIAL);click(SERIAL,'flowStop');reset_fixture('drop' if case=='error' else 'normal')
    workbench(SERIAL);click(SERIAL,'flowRecordTest');time.sleep(.5)
    root=shot(folder,'recording');title=node(root,'teachOverlayTitle').get('text','')
    assert ('Recording' if en else '正在录制') in title,title
    assert ('Automated test' if en else '自动化测试') in node(root,'teachOverlayTimer').get('text','')
    if GUIDANCE:assert ('Next:' if en else '下一步') in node(root,'teachOverlayNext').get('text','')
    if case=='complete' and repeat==1:
        old=node(root,'teachOverlayTitle').get('bounds');press('teachOverlayDock')
        top=shot(folder,'docked');assert old!=node(top,'teachOverlayTitle').get('bounds')
        press('teachOverlayDock')
    sent=[]
    base_route=ROUTE[4:]+ROUTE[:4] if FAN_FIRST else ROUTE
    route=base_route if case in ('complete','wrong_order') else base_route[:4] if case=='error' else base_route[:1]
    if case=='wrong_order':route=[base_route[0],base_route[2],base_route[1]]+base_route[3:]
    for key in route:
        sent.append(click(SERIAL,key,APP));time.sleep(.3)
        if GUIDANCE and case=='complete':
            hint=node(ui(),'teachOverlayNext').get('text','')
            expected=('Finish recording' if en else '结束录制') if len(sent)==8 else ('Next:' if en else '下一步')
            assert expected in hint,(key,hint)
    time.sleep(1.8 if case=='error' else .5)
    root=shot(folder,'before-finish')
    if case=='error':
        assert '停止' in node(root,'teachOverlayTitle').get('text','') if not en else 'stopped' in node(root,'teachOverlayTitle').get('text','')
    elif case=='complete':
        assert ('8 steps' if en else '8 步') in node(root,'teachOverlayTimer').get('text','')
        expected_last=('Save lamp' if en else '保存灯') if FAN_FIRST else ('Save fan' if en else '保存风扇')
        assert expected_last in node(root,'teachOverlayLast').get('text','')
    elif case=='wrong_order':
        assert ('outside' if en else '不符合') in node(root,'teachOverlayNext').get('text','')
    press('teachOverlayCancel' if case=='cancel' else 'teachOverlayFinish');time.sleep(.5)
    root=shot(folder,'result');title=node(root,'teachStateTitle').get('text','')
    expected={'complete':('已结束','ended'),'cancel':('已取消','cancelled'),'incomplete':('不完整','incomplete'),'wrong_order':('不完整','incomplete'),'error':('停止','stopped')}[case][int(en)]
    assert expected in title,(expected,title)
    generate=[n for n in root.iter('node') if n.get('resource-id')==PROBE+':id/teachGenerate']
    assert (len(generate)==1 and generate[0].get('enabled')=='true')==(case=='complete')
    tr=read_trace();assert tr['source']=='AUTOMATED';write(folder/'trace.json',tr)
    if GUIDANCE:
        actions=node(root,'teachRecordedActions').get('text','')
        assert len(re.findall(r'^\d+\. ',actions,re.M))==len(tr['steps']),actions
        assert 'wfLamp' not in actions and 'wfFan' not in actions,actions
    write(folder/'audit.json',json.loads(adb(SERIAL,'shell','run-as',PROBE,'cat','files/workflow-audit-'+tr['traceId']+'.json')))
    write(folder/'oracle.json',json.loads(adb(SERIAL,'shell','run-as',APP,'cat','files/workflow-oracle.json')))
    write(folder/'inputs.json',sent)
    if case=='complete':write(folder/'candidate.json',compile_evidence(tr))
    elif case=='wrong_order':
        try:compile_evidence(tr)
        except ValueError:pass
        else:raise AssertionError('Malformed order unexpectedly compiled')
    row={'case':case,'english':en,'repeat':repeat,'fanFirst':FAN_FIRST,'guidanceChecks':GUIDANCE,'source':tr['source'],'end':tr['end'],'error':tr['error'],'steps':len(tr['steps']),'status':'PASS'}
    write(folder/'result.json',row);print(json.dumps(row),flush=True);return row

def main():
    global GUIDANCE,FAN_FIRST
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['backup','preview','run','handoff']);p.add_argument('--output',type=Path,required=True);p.add_argument('--original',type=Path);p.add_argument('--repeats',type=int,default=1);p.add_argument('--cases',nargs='+',choices=['complete','cancel','incomplete','error','wrong_order'],default=['complete','cancel','incomplete','error']);p.add_argument('--languages',nargs='+',choices=['zh','en'],default=['zh','en']);p.add_argument('--guidance',action='store_true');p.add_argument('--fan-first',action='store_true');p.add_argument('--apk',type=Path,default=Path('android-agent-probe/build/manual/demo-probe-recording-ux-final.apk'));a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    GUIDANCE=a.guidance;FAN_FIRST=a.fan_first
    if a.mode=='backup':backup(a.output);return
    if a.mode=='preview':teaching();shot(a.output,'initial');print(node(ui(),'teachStateTitle').get('text'));return
    if a.mode=='run':
        results=[]
        try:
            for lang in a.languages:
                en=lang=='en'
                for case in a.cases:
                    for repeat in range(1,a.repeats+1):
                        results.append(run_case(a.output,case,en,repeat));write(a.output/'results.json',results)
        finally:
            workbench(SERIAL);click(SERIAL,'flowStop')
        return
    assert a.original
    before=ET.fromstring((a.original/'recorded_workflows.xml').read_text(encoding='utf-8'))
    after=ET.fromstring(adb(SERIAL,'shell','run-as',PROBE,'cat','shared_prefs/recorded_workflows.xml'))
    values=lambda root:{x.get('name'):x.text for x in root}
    assert values(before)==values(after),'Approved skill state changed'
    workbench(SERIAL);click(SERIAL,'flowStop');reset_fixture()
    if GUIDANCE:
        adb(SERIAL,'shell','am','start','-n',PROBE+'/.MainActivity','-f','0x04000000');time.sleep(.6)
        home=shot(a.output,'home')
        assert not any(n.get('resource-id')==PROBE+':id/flowEntry' for n in home.iter('node')),'Advanced tools visible by default'
        press('homeAdvanced');expanded=shot(a.output,'home-advanced');node(expanded,'flowEntry');press('homeAdvanced')
    language(False)
    root=ui()
    if any(n.get('resource-id')==PROBE+':id/teachNew' for n in root.iter('node')):press('teachNew')
    root=shot(a.output,'ready');assert node(root,'teachStateTitle').get('text')=='尚未开始录制';assert node(root,'teachRecord').get('enabled')=='true'
    # Exercise the ordinary user's confirmation, but cancel before creating any
    # HUMAN_DECLARED trace. All actual test demonstrations stay AUTOMATED.
    trace_id=read_trace()['traceId'];press('teachRecord');root=shot(a.output,'start-confirmation')
    assert any('开始新的示范' in n.get('text','') for n in root.iter('node'))
    negative=[n for n in root.iter('node') if n.get('resource-id')=='android:id/button2' and n.get('text')=='取消']
    assert len(negative)==1
    b=list(map(int,re.findall(r'\d+',negative[0].get('bounds',''))));adb(SERIAL,'shell','input','tap',(b[0]+b[2])//2,(b[1]+b[3])//2);time.sleep(.5)
    assert read_trace()['traceId']==trace_id and read_trace()['end']!='RECORDING'
    root=shot(a.output,'ready');assert node(root,'teachRecord').get('enabled')=='true'
    assert read_trace()['end']!='RECORDING'
    bound=adb(SERIAL,'shell','dumpsys','accessibility').split('Bound services:',1)[-1].split('Enabled services:',1)[0]
    assert 'edu.sydney.probe/.ProbeService' in bound
    remote=adb(SERIAL,'shell','pm','path',PROBE).strip().removeprefix('package:');adb(SERIAL,'pull',remote,str(a.output/'installed.apk'))
    candidate=a.apk.read_bytes();assert candidate==(a.output/'installed.apk').read_bytes()
    write(a.output/'handoff.json',{'serviceBound':True,'skillsUnchanged':True,'recording':False,'language':'zh','readyButtonEnabled':True,'startConfirmationCancelPreservesTrace':True,'apkSha256':hashlib.sha256(candidate).hexdigest()})
    print('READY: no recording, service connected, approved skill unchanged, normal fixture')

if __name__=='__main__':main()
