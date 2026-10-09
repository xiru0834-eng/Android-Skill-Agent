"""Run frozen skill on three emulator display configurations and always restore."""
import argparse
import random
import subprocess
import sys
import time
from pathlib import Path
from workflow_experiment import adb,write

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);serial='emulator-5554'
    original=dict(size=adb(serial,'shell','wm','size'),density=adb(serial,'shell','wm','density'))
    if 'Override' in original['size'] or 'Override' in original['density']:raise RuntimeError('Unexpected existing override; do not change')
    configs=[('same-dp','720x1600','280'),('compact','720x1280','420'),('wide','1600x2560','320')]
    random.Random(231).shuffle(configs)
    write(a.output/'protocol.json',dict(original=original,configurations=configs,configurationSeed=231,repeats=4))
    try:
        for label,size,density in configs:
            adb(serial,'shell','wm','size',size);adb(serial,'shell','wm','density',density);time.sleep(2)
            observed=dict(size=adb(serial,'shell','wm','size'),density=adb(serial,'shell','wm','density'))
            write(a.output/(label+'-configuration.json'),observed)
            if size not in observed['size'] or density not in observed['density']:raise RuntimeError('Display change not verified')
            command=[sys.executable,str(Path(__file__).with_name('transfer_run.py')),'--device',serial,'--output',str(a.output/label),'--repeats','4','--allow-experiment']
            subprocess.run(command,check=True,timeout=2400)
            subprocess.run([sys.executable,str(Path(__file__).with_name('transfer_screenshot.py')),
                '--device',serial,'--output',str(a.output/(label+'-final-view'))],check=True,timeout=60)
    finally:
        adb(serial,'shell','wm','size','reset');adb(serial,'shell','wm','density','reset')
        restored=dict(size=adb(serial,'shell','wm','size'),density=adb(serial,'shell','wm','density'))
        write(a.output/'restored.json',restored)
        if restored!=original:raise RuntimeError('Display restoration mismatch')

if __name__=='__main__':main()
