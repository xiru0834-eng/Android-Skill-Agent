"""Close only the stopped experimental emulator, preserving apps and data."""
import argparse
from pathlib import Path
from transfer_run import private
from workflow_capture import APP,PROBE
from workflow_experiment import adb,write


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Refuse overwrite')
    serial='emulator-5554';terminal=private(serial,PROBE,'recorded-workflow-result.json')
    oracle=private(serial,APP,'workflow-oracle.json')
    if terminal.get('status')=='RUNNING' or oracle['events'][-1]['pending']!=0:raise ValueError('Execution still active')
    size=adb(serial,'shell','wm','size');density=adb(serial,'shell','wm','density')
    if 'Override' in size+density or '1080x2400' not in size or '420' not in density:raise ValueError('Display not at original settings')
    evidence=dict(device=serial,size=size,density=density,lastRun=terminal['runId'],lastStatus=terminal['status'],
        currentCase=oracle['caseId'],pending=0,reason='Repeated System UI ANR; no new confirmation trials',dataDeleted=False)
    write(a.output,evidence)
    response=adb(serial,'emu','kill',timeout=15)
    evidence['shutdownResponse']=response;write(a.output,evidence)
    print('Experimental emulator stopped through console; original display verified; app data preserved')


if __name__=='__main__':main()
