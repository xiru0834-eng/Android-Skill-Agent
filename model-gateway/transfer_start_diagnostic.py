"""One separately labelled S3 retry with test-operator UI/tap timings.

Does not replace an original failed case or alter the installed executor.
"""
import argparse
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import workflow_capture
from workflow_experiment import write
from transfer_run import approved,run


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    events=[];original_tree=workflow_capture.tree;original_adb=workflow_capture.adb
    def observed_tree(serial):
        start=time.monotonic();ui=original_tree(serial)
        events.append(dict(kind='operator_tree',ms=round(time.monotonic()*1000),elapsedMs=round((time.monotonic()-start)*1000),xml=ET.tostring(ui,encoding='unicode')))
        write(a.output/'operator-events.json',events);return ui
    def observed_adb(serial,*args,**kwargs):
        start=time.monotonic();result=original_adb(serial,*args,**kwargs)
        events.append(dict(kind='operator_adb',ms=round(time.monotonic()*1000),elapsedMs=round((time.monotonic()-start)*1000),args=args))
        write(a.output/'operator-events.json',events);return result
    workflow_capture.tree=observed_tree;workflow_capture.adb=observed_adb
    case=dict(initial=[1,40,1,3],initialId='S3',fault='normal',condition='S3',repeat=0)
    write(a.output/'protocol.json',dict(device='emulator-5554',suite='normal',cases=[case],diagnosticOnly=True,
        note='Does not replace target-core-v2/run-044; installed executor and task limits unchanged'))
    skill=approved('emulator-5554');write(a.output/'skill.json',skill)
    result=run('emulator-5554',case,a.output/'run-000',skill)
    write(a.output/'results.json',[result]);print(result)


if __name__=='__main__':main()
