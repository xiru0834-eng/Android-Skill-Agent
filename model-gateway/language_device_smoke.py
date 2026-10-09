"""Bilingual UI-to-GPT-to-existing-executor development checks; no approval writes."""
import argparse
import base64
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'evaluation/trace-evidence'))
import device_suite as d
from phone_reuse import reset_fixture

CASES=[
    ('zh_on','打开阅读灯和风扇',[False,False],[True,True],'SUCCEEDED'),
    ('en_off','Turn off the lamp and the fan.',[True,True],[False,False],'SUCCEEDED'),
    ('zh_mix','打开阅读灯，关闭风扇',[False,True],[True,False],'SUCCEEDED'),
    ('en_keep','Turn on the lamp; leave the fan unchanged.',[False,True],[True,True],'SUCCEEDED'),
    ('zh_ambiguous','把那个打开',[False,False],[False,False],'CLARIFY'),
    ('en_unsupported','Set the air conditioner to 24 degrees.',[False,False],[False,False],'REJECT'),
]


def set_text(field,text):
    value=base64.b64encode(text.encode('utf-8')).decode('ascii')
    output=d.s.adb('shell','am','instrument','-w','-e','field',field,'-e','value',value,'edu.sydney.evaluation/.LanguageInput')
    if 'PASS UI text set' not in output: raise RuntimeError('Text entry failed: '+output)


def screen():
    d.s.adb('shell','am','start','-n',d.s.PROBE+'/.MainActivity','-f','0x04000000')
    time.sleep(.6);d.s.click('languageEntry');time.sleep(1.0)
    node=d.s.find(resource=d.s.PROBE+':id/languageInput')
    if node.get('enabled')!='true' or not d.s.visible(node):
        raise RuntimeError('Input page not ready; no submission attempted')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--token-file',type=Path,required=True);parser.add_argument('--first-only',action='store_true')
    args=parser.parse_args()
    if os.environ.get('ANDROID_SERIAL') not in ('emulator-5554','R5CW134LLBZ'): raise RuntimeError('Explicit experimental device required')
    args.output.mkdir(parents=True,exist_ok=False)
    save=lambda name,value:d.s.save(args.output/name,value)
    before=d.s.prefs('two_step_skills');skill=before.get('skill.'+d.BENCH)
    if not skill: raise RuntimeError('Reviewed skill missing; do not bypass approval')
    save('protocol.json',dict(scope='development, UI text injection then normal Execute button; real GPT; independent fixture oracle',cases=CASES,serial=os.environ['ANDROID_SERIAL']))
    screen()
    # Pairing goes through the actual settings field, never preference injection.
    tree=d.s.ui();visible=[n for n in tree.iter('node') if n.get('resource-id')==d.s.PROBE+':id/languagePairing' and d.s.visible(n)]
    if not visible:
        d.s.click('languageSetup',scroll=True)
    d.s.find(resource=d.s.PROBE+':id/languagePairing',scroll=True)
    set_text('languagePairing',args.token_file.read_text(encoding='ascii').strip())
    # Re-open at top; pairing is persisted on submit, so first submit uses this same page.
    rows=[]
    try:
        for index,(name,text,initial,desired,phase) in enumerate(CASES[:1] if args.first_only else CASES):
            if index>0: screen()
            # Fixture setup is external scoring preparation, not agent input.
            reset_fixture('normal',initial)
            if index==0:
                # Reorder existing input Activity preserves unsaved pairing without direct private writes.
                d.s.adb('shell','input','keyevent','KEYCODE_BACK');time.sleep(.3)
            else: screen()
            # Ensure actual entry is foreground after fixture preparation.
            tree=d.s.ui()
            if not any(n.get('resource-id')==d.s.PROBE+':id/languageInput' for n in tree.iter('node')):
                screen()
                d.s.click('languageSetup',scroll=True)
                d.s.find(resource=d.s.PROBE+':id/languagePairing',scroll=True)
                set_text('languagePairing',args.token_file.read_text(encoding='ascii').strip())
            d.s.find(resource=d.s.PROBE+':id/languageInput',scroll=True)
            set_text('languageInput',text)
            try: previous=json.loads(d.s.prefs('language_result').get('last','{}')).get('requestId')
            except Exception: previous=None
            d.s.click('languageExecute',scroll=True)
            start=time.monotonic();report={}
            while time.monotonic()-start<60:
                try: report=json.loads(d.s.prefs('language_result').get('last','{}'))
                except Exception: report={}
                if report.get('requestId')!=previous and report.get('phase') in ('SUCCEEDED','REFUSED','UNCONFIRMED','CLARIFY','REJECT','CANCELLED','ERROR'):break
                time.sleep(.2)
            oracle=d.oracle();actual=[oracle['target'],oracle['other']]
            expected_clicks=[int(a!=b) for a,b in zip(initial,desired)]
            row=dict(name=name,report=report,oracle=oracle,expected=desired,
                passed=report.get('phase')==phase and actual==desired and [oracle['targetClicks'],oracle['otherClicks']]==expected_clicks)
            rows.append(row);save(name+'.json',row);print(json.dumps(row,ensure_ascii=True),flush=True)
            if not row['passed']: break
    finally:
        save('summary.json',dict(completed=len(rows),passed=sum(r['passed'] for r in rows),rows=rows,
            approvalUnchanged=d.s.prefs('two_step_skills').get('skill.'+d.BENCH)==skill))
        screen()
        time.sleep(1.2)  # Capture a settled Activity, not its transition animation.
        d.s.snapshot(args.output/'input-page.png')


if __name__=='__main__':main()
