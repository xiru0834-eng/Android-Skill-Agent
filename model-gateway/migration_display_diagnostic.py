"""Read-only operator geometry diagnostic after a display change; no skill input."""
import argparse
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from workflow_capture import tree, PROBE, APP
from workflow_experiment import adb, write
from transfer_input_ready import ready_window
from migration_matrix import display


def main():
    p = argparse.ArgumentParser(); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=False)
    s = 'emulator-5554'; before = display(s)
    if 'Override' in str(before): raise ValueError('Unexpected override')
    try:
        adb(s, 'shell', 'wm', 'size', '720x1600'); adb(s, 'shell', 'wm', 'density', '280')
        time.sleep(3)
        adb(s, 'shell', 'am', 'start', '-W', '-n', PROBE+'/.MainActivity', '-f', '0x04000000')
        time.sleep(3)
        ui = tree(s)
        node = next(n for n in ui.iter('node') if n.get('resource-id') == PROBE+':id/flowEntry')
        b = list(map(int, re.findall(r'-?\d+', node.get('bounds'))))
        dump = adb(s, 'shell', 'dumpsys', 'input')
        result = dict(display=display(s), node=node.attrib, ui=ET.tostring(ui, encoding='unicode'), input=dump,
            ready=ready_window(dump, PROBE+'/'+PROBE+'.MainActivity', (b[0]+b[2])//2, (b[1]+b[3])//2))
        write(a.output/'geometry.json', result)
        print(json.dumps(dict(node=node.attrib, ready=result['ready'])))
    finally:
        adb(s, 'shell', 'wm', 'size', 'reset'); adb(s, 'shell', 'wm', 'density', 'reset')
        write(a.output/'restored.json', dict(before=before, after=display(s)))


if __name__ == '__main__': main()
