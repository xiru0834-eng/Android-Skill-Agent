"""Verify a draft cannot run; never grants approval."""
import argparse
import json
import time
from pathlib import Path
import xml.etree.ElementTree as ET
from workflow_capture import workbench,click,tree,PROBE,APP
from workflow_experiment import adb,write

def check(serial):
    prefs=ET.fromstring(adb(serial,'shell','run-as',PROBE,'cat','shared_prefs/recorded_workflows.xml'))
    if any(n.get('name')=='approved' for n in prefs):raise RuntimeError('Requires unapproved test state; no existing approval removed')
    before=json.loads(adb(serial,'shell','run-as',APP,'cat','files/workflow-oracle.json'))
    workbench(serial);click(serial,'flowRun')
    # The accessibility observer may briefly return the pre-click tree.
    # Poll only observations; never repeat the attempted execution input.
    for attempt in range(8):
        ui=tree(serial)
        if any('NO_COMPATIBLE_APPROVAL' in n.get('text','') for n in ui.iter('node')):break
        time.sleep(.25)
    else:raise RuntimeError('Denial not shown after bounded observation wait')
    after=json.loads(adb(serial,'shell','run-as',APP,'cat','files/workflow-oracle.json'))
    if before!=after:raise RuntimeError('Unapproved run changed fixture')
    return dict(device=serial,status='PASS',denied=True,fixtureUnchanged=True,approvalGranted=False)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    results=[]
    for serial in ('R5CW134LLBZ','emulator-5554'):
        try:results.append(check(serial))
        except Exception as exc:
            write(args.output/'failure.json',dict(device=serial,error=str(exc),completed=results))
            raise
        write(args.output/'results.json',results)
    write(args.output/'results.json',results);print(json.dumps(results))
