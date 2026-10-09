"""Non-mutating evidence collection after a stopped transfer batch."""
import argparse
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from workflow_capture import tree,APP,PROBE
from workflow_experiment import adb,write,ADB
from transfer_run import private


def main():
    p=argparse.ArgumentParser();p.add_argument('--device',required=True,choices=['R5CW134LLBZ','emulator-5554']);p.add_argument('--output',type=Path,required=True);p.add_argument('--skip-ui',action='store_true');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    for package,name,label in ((PROBE,'recorded-workflow-result.json','latest-result'),(APP,'workflow-oracle.json','current-oracle')):
        write(a.output/(label+'.json'),private(a.device,package,name))
    latest=private(a.device,PROBE,'recorded-workflow-result.json')
    if re.fullmatch('[0-9a-f-]{36}',latest.get('runId','')):
        raw=adb(a.device,'shell','run-as',PROBE,'cat','files/workflow-journal-'+latest['runId']+'.jsonl')
        write(a.output/'late-journal.json',[json.loads(line) for line in raw.splitlines() if line.strip()])
    if a.skip_ui:
        if a.device=='emulator-5554':(a.output/'input-dispatcher.txt').write_text(adb(a.device,'shell','dumpsys','input'),encoding='utf-8')
        for command,filename in ((['dumpsys','accessibility'],'accessibility.txt'),(['logcat','-d','-t','180','-s','ActivityManager','AndroidRuntime','system_server'],'runtime.txt')):
            (a.output/filename).write_text(adb(a.device,'shell',*command),encoding='utf-8')
        print('Private experiment evidence and system error log saved without UI automation');return
    ui=tree(a.device)
    (a.output/'ui.xml').write_text(ET.tostring(ui,encoding='unicode'),encoding='utf-8')
    if not any(n.get('resource-id') in (PROBE+':id/flowRun',APP+':id/wfPage') for n in ui.iter('node')):raise RuntimeError('No allowed experiment foreground; no screenshot')
    screenshot=subprocess.run([str(ADB),'-s',a.device,'exec-out','screencap','-p'],capture_output=True,check=True,timeout=15).stdout
    (a.output/'screen.png').write_bytes(screenshot)
    for command,filename in ((['dumpsys','accessibility'],'accessibility.txt'),(['logcat','-d','-t','250','-s','AndroidRuntime'],'runtime.txt')):
        (a.output/filename).write_text(adb(a.device,'shell',*command),encoding='utf-8')
    if a.device=='emulator-5554':
        for command,filename in ((['dumpsys','input'],'input-dispatcher.txt'),(['logcat','-d','-t','600','-s','InputDispatcher','WindowManager','ActivityTaskManager'],'input-transitions.txt')):
            (a.output/filename).write_text(adb(a.device,'shell',*command),encoding='utf-8')
    print(ET.tostring(ui,encoding='unicode'))


if __name__=='__main__':main()
