"""Import a compiled candidate through Android's document picker. Never approve or run."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'evaluation/trace-evidence'))
import device_suite as d
from qualify import approvals
from contracts import load_json, require, to_v2


def wait_picker(read=d.s.ui, sleep=time.sleep):
    for attempt in range(8):
        tree = read()
        if any(n.get('resource-id', '').startswith(('com.google.android.documentsui:', 'com.android.documentsui:'))
               for n in tree.iter('node')):
            return tree
        if attempt < 7: sleep(.25)
    raise RuntimeError('Picker did not become visible; import input was not repeated')


def open_picker(click, read=d.s.ui, sleep=time.sleep):
    # A tree may already expose final bounds while the new Activity is animating.
    # Preparation only: settle before the single input, never repeat the input.
    sleep(1.0)
    click()
    return wait_picker(read, sleep)


def select_file(filename):
    tree = open_picker(lambda: d.s.click('twoImport'))
    if not any(n.get('text') == 'Downloads' for n in tree.iter('node')):
        roots = [n for n in tree.iter('node') if n.get('content-desc') == 'Show roots']
        require(len(roots) == 1, 'PICKER_ROOTS')
        d.s.S.tap_node(roots[0]); time.sleep(.3)
        d.s.S.tap_node(d.s.find(resource='android:id/title', text='Downloads')); time.sleep(.3)
    tree = d.s.ui()
    grid = [n for n in tree.iter('node') if n.get('content-desc') == 'List view']
    if len(grid) == 1: d.s.S.tap_node(grid[0]); time.sleep(.3)
    for _ in range(8):
        tree = d.s.ui()
        matches = [n for n in tree.iter('node') if n.get('text') == filename and d.s.visible(n)]
        require(len(matches) <= 1, 'AMBIGUOUS_FILE')
        if matches:
            d.s.S.tap_node(matches[0]); time.sleep(.5); return
        panels = [n for n in tree.iter('node') if n.get('resource-id', '').endswith(':id/dir_list')]
        require(len(panels) == 1, 'PICKER_LIST')
        x1,y1,x2,y2 = map(int, re.findall(r'\d+', panels[0].get('bounds')))
        d.s.adb('shell','input','swipe',(x1+x2)//2,int(y1+.8*(y2-y1)),(x1+x2)//2,int(y1+.3*(y2-y1)),250)
    raise RuntimeError('Candidate file not found in picker')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--job', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--allow-phone-import', action='store_true'); args = p.parse_args()
    require(args.allow_phone_import, 'PHONE_CONSENT_REQUIRED')
    trace = load_json((args.job/'trace.json').read_text(encoding='utf-8'))
    audit = load_json((args.job/'audit.json').read_text(encoding='utf-8'))
    skill = load_json((args.job/'skill-v2.json').read_text(encoding='utf-8'))
    require(audit['status'] == 'candidate' and audit['review_status'] == 'UNREVIEWED', 'NOT_CANDIDATE')
    require(audit['trace_sha256'] == hashlib.sha256((args.job/'trace.json').read_bytes()).hexdigest(), 'TRACE_CHANGED')
    require(skill == to_v2(audit['model']['draft'], trace), 'FILE_CHANGED')
    require(skill['appPackage'] == d.BENCH, 'FIRST_PHONE_SLICE_BENCH_ONLY')
    args.output.mkdir(parents=True, exist_ok=False)
    save = lambda name, value: d.s.save(args.output/name, value)
    before = approvals(); save('approvals-before.json', before)
    save('draft-before.json', d.s.prefs('two_step_skills'))
    filename = 'gpt-draft-'+str(uuid.uuid4())+'.json'
    destination = '/sdcard/Download/'+filename
    save('protocol.json', dict(sourceJob=str(args.job.resolve()), phoneFile=destination,
                               approve=False, run=False, skill=skill))
    try:
        d.s.adb('push', str(args.job/'skill-v2.json'), destination)
        d.main_screen(); d.s.click('selectBench'); d.two_screen(); select_file(filename)
        message = d.s.find(resource='android:id/message').get('text', '')
        require(all(s['resourceId'] in message for s in skill['steps']), 'IMPORT_PREVIEW_MISMATCH')
        require(d.s.find(resource='android:id/button1').get('text', '').casefold() == 'import draft', 'IMPORT_BUTTON')
        d.s.click('button1', pkg='android'); time.sleep(.4)
        current = d.s.prefs('two_step_skills')
        require(json.loads(current['draft.'+d.BENCH]) == skill, 'IMPORTED_DATA_MISMATCH')
        require(current['origin.'+d.BENCH] == 'true' and 'check.'+d.BENCH not in current, 'IMPORT_REVIEW_GATE')
        require(before == approvals(), 'IMPORT_CHANGED_APPROVAL')
        old_state = d.oracle()
        d.two_screen(); d.s.click('twoCheck'); time.sleep(1.2)
        current = d.s.prefs('two_step_skills')
        require(current.get('reason.'+d.BENCH) == 'READY', 'BINDING_CHECK_FAILED')
        require(old_state == d.oracle(), 'BINDING_CHECK_SENT_INPUT')
        after = approvals(); require(before == after, 'CHECK_CHANGED_APPROVAL')
        save('approvals-after.json', after)
        save('result.json', dict(status='IMPORTED_UNAPPROVED', bindings='READY',
                                approvalsPreserved=True, bindingCheckInputs=0, humanApproval=False))
        d.two_screen()
        print('IMPORTED_UNAPPROVED; bindings READY; existing approvals unchanged; no execution')
    except Exception as error:
        save('failure.json', dict(errorType=type(error).__name__, reason=str(error)))
        raise


if __name__ == '__main__': main()
