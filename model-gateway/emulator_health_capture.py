"""Read-only diagnostic snapshots of this experimental emulator."""
import argparse
import subprocess
from pathlib import Path
from workflow_experiment import adb,ADB,write

p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
for name,args in {'window':['dumpsys','window'],'lastanr':['dumpsys','activity','lastanr'],
                  'cpu':['dumpsys','cpuinfo'],'input':['dumpsys','input'],
                  'memory':['cat','/proc/meminfo'],'accessibility':['dumpsys','accessibility']}.items():
    (a.output/(name+'.txt')).write_text(adb('emulator-5554','shell',*args,timeout=12),encoding='utf-8')
(a.output/'screen.png').write_bytes(subprocess.check_output([str(ADB),'-s','emulator-5554','exec-out','screencap','-p'],timeout=20))
print('Captured emulator health, no UI input.')
