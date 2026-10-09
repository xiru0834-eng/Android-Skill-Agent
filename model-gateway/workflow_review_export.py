"""Normal UI review/export for an explicitly authorized experimental skill."""
import argparse
import json
import re
from pathlib import Path
from workflow_capture import workbench,click,tree,PROBE
from workflow_import import tap
from workflow_experiment import adb,write
from transfer_run import approved

def main():
    p=argparse.ArgumentParser();p.add_argument('--device',choices=['R5CW134LLBZ','emulator-5554'],required=True)
    p.add_argument('--skill',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--export-name');p.add_argument('--allow-review',action='store_true');a=p.parse_args()
    if not a.allow_review:p.error('Explicit experimental review authorization required')
    if a.export_name and not re.fullmatch(r'[a-z0-9-]+\.json',a.export_name):p.error('Simple JSON filename required')
    a.output.mkdir(parents=True,exist_ok=False);skill=json.loads(a.skill.read_text(encoding='utf-8'));s=a.device
    import xml.etree.ElementTree as ET
    prefs=ET.fromstring(adb(s,'shell','run-as',PROBE,'cat','shared_prefs/recorded_workflows.xml'))
    draft=json.loads(next(n.text for n in prefs if n.get('name')=='draft'))
    if draft!=skill:raise RuntimeError('Unexpected draft')
    workbench(s);click(s,'flowReview');ui=tree(s)
    if not any('Review workflow' in n.get('text','') for n in ui.iter('node')):raise RuntimeError('Review dialog missing')
    if not any(skill['goal'] in n.get('text','') for n in ui.iter('node')):raise RuntimeError('Review meaning mismatch')
    write(a.output/'review-dialog.json',[n.attrib for n in ui.iter('node')]);click(s,'button1','android')
    if approved(s)!=skill:raise RuntimeError('Review did not persist exact draft')
    write(a.output/'approval.json',dict(method='normal UI review/save',skill=skill,device=s))
    if a.export_name:
        files=adb(s,'shell','ls','/sdcard/Download')
        if a.export_name in files.splitlines():raise RuntimeError('Export filename already exists')
        click(s,'flowExport');ui=tree(s)
        if not any(n.get('text')=='Downloads' for n in ui.iter('node')):raise RuntimeError('Unexpected export folder')
        fields=[n for n in ui.iter('node') if n.get('class')=='android.widget.EditText']
        if len(fields)!=1:raise RuntimeError('Filename field ambiguous')
        tap(s,fields[0]);adb(s,'shell','input','keycombination','113','29');adb(s,'shell','input','text',a.export_name)
        if not any(n.get('text')==a.export_name and n.get('class')=='android.widget.EditText' for n in tree(s).iter('node')):raise RuntimeError('Filename input failed')
        click(s,'button1','android');target=a.output/a.export_name
        adb(s,'pull','/sdcard/Download/'+a.export_name,str(target))
        if json.loads(target.read_text(encoding='utf-8'))!=skill:raise RuntimeError('Export differs from approved skill')
    print('REVIEWED via normal UI'+('; EXPORTED exact skill' if a.export_name else ''))

if __name__=='__main__':main()
