"""Controlled regression: opening an existing workflow must preserve its session."""
import argparse
import json
import time
from pathlib import Path
from workflow_experiment import adb, write

APP = 'edu.sydney.transferlab'

def read(serial):
    return json.loads(adb(serial, 'shell', 'run-as', APP, 'cat', 'files/workflow-oracle.json'))

def main():
    p=argparse.ArgumentParser();p.add_argument('--device', required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    adb(a.device,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','caseId','0123456789abcdef',
        '--es','layout','multi','--es','initial','0,40,0,3','--es','fault','drop')
    time.sleep(.5);before=read(a.device);write(a.output/'before.json',before)
    adb(a.device,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','layout','multi')
    time.sleep(.5);after=read(a.device);write(a.output/'after.json',after)
    checks={'sameCase':after['caseId']==before['caseId'],'sameInitial':after['initial']==before['initial'],
            'historyPreserved':after['events'][:len(before['events'])]==before['events'],
            'faultPreserved':after.get('fault')=='drop'}
    write(a.output/'result.json',checks);print(json.dumps(checks))
    if not all(checks.values()):raise SystemExit(1)

if __name__=='__main__':main()
