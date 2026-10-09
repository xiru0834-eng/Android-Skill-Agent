"""Display validation of one reviewed package; no model, approval writes or retuning."""
import argparse
import hashlib
import math
import random
import statistics
import subprocess
import time
from pathlib import Path

from transfer_cases import INITIALS
from transfer_run import approved, run
from workflow_capture import APP, PROBE, tree
from workflow_experiment import adb, write, ADB

CONFIGS = {'reference': ('1080x2400', '420'), 'same-dp': ('720x1600', '280'),
           'compact': ('720x1280', '420'), 'wide': ('1600x2560', '320')}


def make_blocks():
    rng = random.Random(28119)
    blocks = []
    for repeat in range(3):
        names = list(CONFIGS)
        rng.shuffle(names)
        for name in names:
            cases = [dict(initial=list(v), initialId='S'+str(i), fault='normal',
                          condition='S'+str(i), repeat=repeat) for i, v in enumerate(INITIALS)]
            rng.shuffle(cases)
            blocks.append(dict(config=name, repeat=repeat, cases=cases))
    return blocks


def summarize(rows, planned):
    valid = [r for r in rows if r.get('evidence_complete')]
    def group(items):
        times = sorted(r['elapsed_ms'] for r in items if 'elapsed_ms' in r)
        return dict(scored=len(items), confirmed=sum(bool(r.get('confirmed_success')) for r in items),
                    falseSuccess=sum(bool(r.get('false_success')) for r in items),
                    p50ms=statistics.median(times) if times else None,
                    p95ms=times[math.ceil(.95*len(times))-1] if times else None)
    result = dict(planned=planned, attempted=len(rows), unrun=planned-len(rows),
                  infrastructureFailures=len(rows)-len(valid), **group(valid))
    result['byConfig'] = {}
    for name in CONFIGS:
        items = [r for r in valid if r['config'] == name]
        result['byConfig'][name] = dict(**group(items),
            already=group([r for r in items if r['case']['initialId'] == 'S5']),
            needsInput=group([r for r in items if r['case']['initialId'] != 'S5']))
    return result


def remaining_blocks(blocks, attempted):
    total = sum(len(b['cases']) for b in blocks)
    if not 0 <= attempted <= total: raise ValueError('Invalid attempted count')
    result = []
    for block in blocks:
        count = len(block['cases'])
        if attempted >= count:
            attempted -= count
        else:
            result.append(dict(block, cases=block['cases'][attempted:]))
            attempted = 0
    return result


def display(serial):
    return dict(size=adb(serial, 'shell', 'wm', 'size'), density=adb(serial, 'shell', 'wm', 'density'))


def effective_display_value(raw):
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    overrides = [line.split(': ', 1)[1] for line in lines if line.startswith('Override ') and ': ' in line]
    physical = [line.split(': ', 1)[1] for line in lines if line.startswith('Physical ') and ': ' in line]
    if len(overrides) > 1 or len(physical) != 1: raise ValueError('Malformed wm response')
    return overrides[0] if overrides else physical[0]


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--smoke', action='store_true')
    p.add_argument('--start-at', type=int, default=0)
    p.add_argument('--config', choices=list(CONFIGS))
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    serial = 'emulator-5554'
    original = display(serial)
    if 'Override' in str(original): raise RuntimeError('Unexpected display override')
    skill = approved(serial)
    if skill['finalGoals'] != [1, 60, 1, 1]: raise RuntimeError('Unexpected frozen goals')
    write(a.output/'skill.json', skill)
    blocks = make_blocks() if not a.smoke else [dict(config='reference', repeat=0,
        cases=[dict(initial=list(INITIALS[0]), initialId='S0', condition='S0', fault='normal', repeat=0)])]
    blocks = remaining_blocks(blocks, a.start_at)
    if a.config:
        if a.start_at: p.error('Do not mix filtered batch with resumed full matrix')
        if a.smoke: blocks[0]['config'] = a.config
        else: blocks = [b for b in blocks if b['config'] == a.config]
    planned = sum(len(b['cases']) for b in blocks)
    write(a.output/'protocol.json', dict(original=original, blocks=blocks, planned=planned,
        modelCalls=0, seed=28119, budgetMs=30000, inference='none', smoke=a.smoke, startAt=a.start_at,
        selectedConfig=a.config, preparation='Controller warm launch and read-only UI observation after display switch; task executor unchanged',
        hashes={f.name: hashlib.sha256(f.read_bytes()).hexdigest() for f in Path(__file__).parent.glob('*.py')}))
    rows = []
    try:
        for index, block in enumerate(blocks):
            label = block['config']
            size, density = CONFIGS[label]
            adb(serial, 'shell', 'am', 'force-stop', APP)
            adb(serial, 'shell', 'wm', 'size', size)
            adb(serial, 'shell', 'wm', 'density', density)
            time.sleep(3)
            actual = display(serial)
            write(a.output/f'block-{index:02d}-display.json', actual)
            if size != effective_display_value(actual['size']) or density != effective_display_value(actual['density']):
                raise RuntimeError('Display override not observed')
            # Test operator preparation only: no target control input, no approval writes.
            launched = adb(serial, 'shell', 'am', 'start', '-W', '-n', PROBE+'/.MainActivity', '-f', '0x04000000')
            write(a.output/f'block-{index:02d}-launch.json', dict(response=launched))
            if 'Status: ok' not in launched: raise RuntimeError('Operator Activity did not start normally')
            time.sleep(3)
            import xml.etree.ElementTree as ET
            write(a.output/f'block-{index:02d}-operator-preparation.json', dict(launch=launched,
                ui=ET.tostring(tree(serial), encoding='unicode'), input=adb(serial, 'shell', 'dumpsys', 'input')))
            for case in block['cases']:
                directory = a.output/f'run-{len(rows):03d}'
                try:
                    value = run(serial, case, directory, skill)
                except Exception as error:
                    value = dict(case=case, evidence_complete=False, infrastructureFailure=str(error))
                    directory.mkdir(exist_ok=True)
                    write(directory/'failure.json', value)
                    rows.append(dict(config=label, **value))
                    write(a.output/'results.json', rows)
                    raise
                rows.append(dict(config=label, **value))
                write(a.output/'results.json', rows)
                write(a.output/'summary.json', summarize(rows, planned))
                print(f"{len(rows)}/{planned} {label} {case['initialId']} {value['status']} {value['reason']} {value['elapsed_ms']}ms", flush=True)
            screenshot = subprocess.run([str(ADB), '-s', serial, 'exec-out', 'screencap', '-p'], capture_output=True, check=True, timeout=20)
            (a.output/f'block-{index:02d}-screen.png').write_bytes(screenshot.stdout)
    except Exception as error:
        write(a.output/'aborted.json', dict(error=str(error), completed=len(rows)))
        raise
    finally:
        write(a.output/'summary.json', summarize(rows, planned))
        adb(serial, 'shell', 'wm', 'size', 'reset')
        adb(serial, 'shell', 'wm', 'density', 'reset')
        restored = display(serial)
        write(a.output/'restored.json', dict(actual=restored, matches=restored == original))
        if restored != original: raise RuntimeError('Display restoration mismatch')


if __name__ == '__main__': main()
