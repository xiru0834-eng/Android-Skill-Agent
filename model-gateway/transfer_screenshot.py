"""Read-only visual evidence, restricted to the foreground experiment workflow."""
import argparse
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from workflow_capture import tree,APP
from workflow_experiment import ADB,write
from transfer_run import private


def main():
    p=argparse.ArgumentParser();p.add_argument('--device',choices=['R5CW134LLBZ','emulator-5554'],required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    ui=tree(a.device)
    if not any(n.get('resource-id')==APP+':id/wfPage' for n in ui.iter('node')):raise RuntimeError('Not the allowed workflow page')
    before=private(a.device,APP,'workflow-oracle.json')
    picture=subprocess.run([str(ADB),'-s',a.device,'exec-out','screencap','-p'],capture_output=True,check=True,timeout=15).stdout
    after=private(a.device,APP,'workflow-oracle.json')
    final_ui=tree(a.device)
    if not any(n.get('resource-id')==APP+':id/wfPage' for n in final_ui.iter('node')):raise RuntimeError('Foreground changed')
    if before!=after:raise RuntimeError('State changed during screenshot; image not archived')
    (a.output/'screen.png').write_bytes(picture)
    (a.output/'ui.xml').write_text(ET.tostring(ui,encoding='unicode'),encoding='utf-8')
    write(a.output/'state.json',after)
    print('Experiment-only screenshot and state saved')


if __name__=='__main__':main()
