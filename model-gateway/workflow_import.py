"""Stage only an unapproved workflow via Android's normal local document picker."""
import argparse
import hashlib
import json
import re
import time
import uuid
from pathlib import Path
from workflow_capture import tree, click, workbench, PROBE
from workflow_experiment import adb, write

def tap(serial,node):
    b=list(map(int,re.findall(r'-?\d+',node.get('bounds',''))))
    if len(b)!=4 or b[2]<=b[0] or b[3]<=b[1]:raise RuntimeError('Not visible')
    adb(serial,'shell','input','tap',(b[0]+b[2])//2,(b[1]+b[3])//2);time.sleep(.6)

def pick(serial,filename):
    time.sleep(.6);ui=tree(serial)
    for _ in range(8):
        if any(n.get('resource-id','').startswith(('com.google.android.documentsui:','com.android.documentsui:')) for n in ui.iter('node')):break
        time.sleep(.25);ui=tree(serial)
    else:raise RuntimeError('Document picker did not open; input not repeated')
    if not any(n.get('text')=='Downloads' for n in ui.iter('node')):
        roots=[n for n in ui.iter('node') if n.get('content-desc')=='Show roots']
        if len(roots)!=1:raise RuntimeError('Document roots unavailable')
        tap(serial,roots[0]);ui=tree(serial)
        downloads=[n for n in ui.iter('node') if n.get('text')=='Downloads' and n.get('resource-id')=='android:id/title']
        if len(downloads)!=1:raise RuntimeError('Downloads unavailable')
        tap(serial,downloads[0])
    for _ in range(10):
        ui=tree(serial);matches=[n for n in ui.iter('node') if n.get('text')==filename]
        if len(matches)==1:
            tap(serial,matches[0]);return
        if len(matches)>1:raise RuntimeError('Ambiguous filename')
        panels=[n for n in ui.iter('node') if n.get('resource-id','').endswith(':id/dir_list')]
        if len(panels)!=1:raise RuntimeError('Document list unavailable')
        b=list(map(int,re.findall(r'\d+',panels[0].get('bounds',''))))
        adb(serial,'shell','input','swipe',(b[0]+b[2])//2,int(b[1]+.8*(b[3]-b[1])),(b[0]+b[2])//2,int(b[1]+.3*(b[3]-b[1])),250)
    raise RuntimeError('File not found')

def main():
    p=argparse.ArgumentParser();p.add_argument('--device',choices=['R5CW134LLBZ','emulator-5554'],required=True)
    p.add_argument('--skill',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--allow-import',action='store_true');args=p.parse_args()
    if not args.allow_import:p.error('Import consent required')
    args.output.mkdir(parents=True,exist_ok=False);raw=args.skill.read_bytes();skill=json.loads(raw)
    if skill.get('kind')!='WORKFLOW_SKILL':raise ValueError('Not a workflow')
    filename='a-workflow-'+str(uuid.uuid4())+'.json';serial=args.device
    write(args.output/'protocol.json',dict(device=serial,file=filename,sha256=hashlib.sha256(raw).hexdigest(),approve=False,execute=False))
    adb(serial,'push',str(args.skill),'/sdcard/Download/'+filename)
    workbench(serial);click(serial,'flowImport');pick(serial,filename)
    ui=tree(serial);titles=[n for n in ui.iter('node') if 'Import unreviewed workflow?' in n.get('text','')]
    if len(titles)!=1:raise RuntimeError('Expected draft confirmation missing')
    click(serial,'button1','android')
    prefs=adb(serial,'shell','run-as',PROBE,'cat','shared_prefs/recorded_workflows.xml')
    import xml.etree.ElementTree as ET
    data={n.get('name'):n.text for n in ET.fromstring(prefs)}
    if json.loads(data['draft'])!=skill:raise RuntimeError('Imported draft mismatch')
    write(args.output/'result.json',dict(status='IMPORTED_UNREVIEWED',draft=skill,hasExistingApproval='approved' in data))
    print('IMPORTED_UNREVIEWED; no approval granted and no workflow executed')

if __name__=='__main__':main()
