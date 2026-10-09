"""Negative UI checks: no target input and no new run after rejection/cancellation."""
import json
import re
import time
from pathlib import Path
from named_journey_device import prefs,fixture,library,tap,text,snap,home,PROBE
from workflow_capture import tree
from workflow_experiment import adb,write
from transfer_run import audited

def at(serial,key):
    nodes=[n for n in tree(serial).iter('node') if n.get('resource-id')==PROBE+':id/'+key]
    if len(nodes)!=1:raise RuntimeError('Missing UI control '+key)
    b=list(map(int,re.findall(r'-?\d+',nodes[0].get('bounds',''))));assert b[2]>b[0] and b[3]>b[1]
    return (b[0]+b[2])//2,(b[1]+b[3])//2

def negative(serial,mode,out):
    out.mkdir(parents=True,exist_ok=False);before=fixture(serial,[0,40,0,3]);old=prefs(serial).get('result')
    library(serial);text(serial,'libraryInput','Turn on the lamp.' if mode=='reject' else 'Run Reading60.')
    choose=at(serial,'libraryChoose');cancel=at(serial,'libraryCancel')
    adb(serial,'shell','input','tap',*choose)
    if mode=='cancel':adb(serial,'shell','input','tap',*cancel)
    elif mode=='exit':adb(serial,'shell','input','keyevent','4')
    if mode=='confirm-cancel':
        for _ in range(40):
            ui=tree(serial)
            if any(n.get('resource-id')=='android:id/button2' for n in ui.iter('node')):break
            time.sleep(.5)
        else:raise RuntimeError('No confirmation shown')
        snap(serial,out/'confirmation.png');tap(serial,'button2','android')
    time.sleep(8)
    ui=tree(serial);snap(serial,out/'after.png');state=prefs(serial);oracle=audited(serial)
    inputs=[e for e in oracle['oracle']['events'] if e['kind'].startswith(('input:','edit:'))]
    assert oracle['oracle']['caseId']==before['caseId'] and not inputs and old==state.get('result')
    assert not any(n.get('resource-id')=='android:id/button1' for n in ui.iter('node'))
    if mode=='reject':
        status=next(n.get('text','') for n in ui.iter('node') if n.get('resource-id')==PROBE+':id/libraryStatus')
        assert status.startswith(('clarify','reject'))
    write(out/'evidence.json',dict(mode=mode,before=before,after=oracle,resultUnchanged=True,inputs=inputs,passCriteria=True))
    print('SAFETY PASS '+mode,flush=True)

def persistence(serial,out):
    out.mkdir(parents=True,exist_ok=False);before=prefs(serial)
    adb(serial,'shell','am','force-stop',PROBE);library(serial);time.sleep(2)
    after=prefs(serial);assert before.get('library')==after.get('library') and before.get('approved')==after.get('approved')
    snap(serial,out/'restarted.png');tap(serial,'libraryLanguage');snap(serial,out/'other-language.png');tap(serial,'libraryLanguage')
    assert prefs(serial)['library']==before['library']
    write(out/'evidence.json',dict(catalog=json.loads(before['library']),restartPreserved=True,languageSwitchPreserved=True))
    print('PERSISTENCE PASS',flush=True)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['reject','cancel','exit','confirm-cancel','persistence']);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='persistence':persistence('R5CW134LLBZ',a.output)
    else:negative('R5CW134LLBZ',a.mode,a.output)
