"""Read-only isolated-AVD failure evidence; no recovery, approval or model calls."""
import argparse
import re
from pathlib import Path
import task3_device_checks as device
from workflow_experiment import write


def probe_main_stack(raw):
    for section in raw.replace('\r\n','\n').split('Cmd line: ')[1:]:
        if not section.startswith('edu.sydney.probe\n'):continue
        match=re.search(r'^"main"[^\n]*\n.*?(?=^"[^\n]+"|\Z)',section,re.S|re.M)
        if match:return 'Cmd line: edu.sydney.probe\n'+match.group(0)
    return None


def capture(out):
    out.mkdir(parents=True,exist_ok=False);write(out/'device.json',device.gate())
    write(out/'preserved-state.json',device.prefs(device.SERIAL))
    for name,args in [('input',['dumpsys','input']),('last-anr',['dumpsys','activity','lastanr']),('cpu',['dumpsys','cpuinfo']),('processes',['ps','-A'])]:
        write(out/(name+'.json'),dict(raw=device.adb(device.SERIAL,'shell',*args),readOnly=True))
    raw=device.adb(device.SERIAL,'shell','dumpsys','dropbox','--print','data_app_anr',timeout=20)
    # Keep only this experiment app's main-thread section; other process stacks
    # are not needed to justify a stopped Task3 sample.
    write(out/'probe-anr-main.json',dict(stack=probe_main_stack(raw),
        symptomNotRootCause=True,readOnly=True,paidCalls=0))
    try:device.snap(device.SERIAL,out/'screen.png')
    except RuntimeError as error:
        if str(error)!='No allowed UI evidence':raise
        write(out/'screen-scope.json',dict(reason=str(error),controllerNotReady=True,screenshotRetained=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);capture(p.parse_args().output)
