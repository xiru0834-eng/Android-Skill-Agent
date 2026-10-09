"""ADB-driven recording regression. No review, model call or skill execution."""
import argparse
import json
import time
from pathlib import Path
from workflow_capture import APP, PROBE, click, workbench, tree
from workflow_experiment import adb, write
from workflow_contract import compile_evidence

ROUTE=['wfOpenLamp','wfLampPower','wfLampValue60','wfLampSave','wfOpenFan','wfFanPower','wfFanValue1','wfFanSave']
CASES={
    'normal':('normal',ROUTE),
    'selected_again':('normal',['wfOpenLamp','wfLampValue40']+ROUTE[1:]),
    'layout_roundtrip':('normal',['wfSingle','wfMulti']+ROUTE),
    'navdelay':('navdelay',ROUTE),
    'save_delay':('delay',ROUTE),
    'drop_save':('drop',ROUTE[:4]),
    'single_edit':('normal',['wfSingle','wfLampPower']),
    'selected_fan_again':('normal',ROUTE[:7]+['wfFanValue1','wfFanSave']),
    'same_layout':('normal',['wfMulti']+ROUTE),
}

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--cases',nargs='+',choices=CASES,required=True);p.add_argument('--repeats',type=int,default=1)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False);serial='R5CW134LLBZ';results=[]
    for name in args.cases:
        for repeat in range(args.repeats):
            folder=args.output/f'{name}-{repeat+1}';folder.mkdir();fault,route=CASES[name];submitted=[]
            try:
                workbench(serial);click(serial,'flowStop')
                adb(serial,'shell','am','start','-W','-n',APP+'/.WorkflowActivity','--es','layout','multi','--es','initial','0,40,0,3','--es','fault',fault)
                time.sleep(.7);workbench(serial);click(serial,'flowRecordTest');time.sleep(1)
                for key in route:
                    submitted.append(click(serial,key,APP))
                    time.sleep(.6)
                    tr=json.loads(adb(serial,'shell','run-as',PROBE,'cat','files/workflow-trace.json'))
                    if tr['end']!='RECORDING':break
                time.sleep(1.7);workbench(serial);click(serial,'flowStop')
                tr=json.loads(adb(serial,'shell','run-as',PROBE,'cat','files/workflow-trace.json'));write(folder/'trace.json',tr)
                write(folder/'oracle.json',json.loads(adb(serial,'shell','run-as',APP,'cat','files/workflow-oracle.json')))
                write(folder/'inputs.json',submitted)
                try:
                    audit=json.loads(adb(serial,'shell','run-as',PROBE,'cat','files/workflow-audit-'+tr['traceId']+'.json'));write(folder/'audit.json',audit)
                except Exception:pass
                try:skill=compile_evidence(tr);write(folder/'candidate.json',skill);valid=True;reason=''
                except Exception as e:valid=False;reason=str(e)
                row=dict(case=name,repeat=repeat+1,end=tr['end'],error=tr['error'],steps=len(tr['steps']),compiled=valid,compileReason=reason,source=tr['source'])
            except Exception as e:
                row=dict(case=name,repeat=repeat+1,harnessError=str(e))
            results.append(row);write(folder/'result.json',row);write(args.output/'results.json',results);print(json.dumps(row),flush=True)
    workbench(serial)

if __name__=='__main__':main()
