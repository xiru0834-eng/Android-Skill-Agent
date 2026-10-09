"""UI locale switch retains text and never executes; bilingual real invocation regression."""
import argparse
import json
import os
from pathlib import Path
import time
from language_device_smoke import d,screen,set_text,reset_fixture
from language_safety_smoke import report,wait_done


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--run',action='store_true');args=p.parse_args()
    if os.environ.get('ANDROID_SERIAL') not in ('emulator-5554','R5CW134LLBZ'):raise RuntimeError('Explicit test device required')
    args.output.mkdir(parents=True,exist_ok=False);rows=[]
    for english,text,desired in [(True,'打开阅读灯和风扇',[True,True]),(False,'Turn off the lamp and fan.',[False,False])]:
        reset_fixture('normal',[not desired[0],not desired[1]]);screen();set_text('languageInput',text)
        initial=d.oracle()
        # Toggle twice to prove preservation in both directions, ending at requested language.
        for _ in range(2): d.s.click('languageToggle');time.sleep(.15)
        label=d.s.find(resource=d.s.PROBE+':id/languageToggle').get('text')
        if (label=='中文')!=english:d.s.click('languageToggle')
        tree=d.s.ui();value=d.s.S.find(tree,resource=d.s.PROBE+':id/languageInput').get('text')
        label=d.s.S.find(tree,resource=d.s.PROBE+':id/languageExecute').get('text')
        assert value==text and label==('Execute' if english else '执行') and d.oracle()==initial
        time.sleep(1);d.s.snapshot(args.output/('english.png' if english else 'chinese.png'))
        row=dict(english=english,inputPreserved=True,toggleNoAction=True)
        if args.run:
            old=report().get('requestId');d.s.click('languageExecute',scroll=True);r=wait_done(old);o=d.oracle()
            row.update(report=r,oracle=o,passed=r['phase']=='SUCCEEDED' and [o['target'],o['other']]==desired)
        rows.append(row);print(json.dumps(row,ensure_ascii=True),flush=True)
    d.s.save(args.output/'summary.json',dict(rows=rows))
    screen();time.sleep(1.0)
    d.s.snapshot(args.output/'ready.png')


if __name__=='__main__': main()
