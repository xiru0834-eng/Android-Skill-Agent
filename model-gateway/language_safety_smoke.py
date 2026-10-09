"""Device cancellation / disconnected bridge / already-at-goal development checks."""
import argparse
import json
import os
from pathlib import Path
import time
from language_device_smoke import d,screen,set_text,reset_fixture


def report():
    return json.loads(d.s.prefs('language_result').get('last','{}'))


def wait_done(previous):
    for _ in range(260):
        r=report()
        if r.get('requestId')!=previous and r.get('phase') not in ('UNDERSTANDING','OPENING','EXECUTING',None):return r
        time.sleep(.2)
    raise RuntimeError('No terminal result')


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    if os.environ.get('ANDROID_SERIAL')!='emulator-5554':raise RuntimeError('Emulator only')
    args.output.mkdir(parents=True,exist_ok=False);rows=[]
    def save(name,r,expected,initial):
        o=d.oracle();row=dict(name=name,report=r,oracle=o,passed=r['phase']==expected and
            [o['target'],o['other']]==initial and o['targetClicks']==o['otherClicks']==0)
        rows.append(row);d.s.save(args.output/(name+'.json'),row);print(json.dumps(row,ensure_ascii=True),flush=True)
    try:
        reset_fixture('normal',[False,False]);screen();set_text('languageInput','打开灯和风扇')
        # Fetch both visible control coordinates before sending; avoid observer latency between clicks.
        tree=d.s.ui();execute=d.s.S.find(tree,resource=d.s.PROBE+':id/languageExecute');stop=d.s.S.find(tree,resource=d.s.PROBE+':id/languageStop')
        d.s.S.tap_node(execute);time.sleep(.15);d.s.S.tap_node(stop)
        time.sleep(7);save('cancel_late_response',report(),'CANCELLED',[False,False])
        reset_fixture('normal',[False,False]);screen();set_text('languageInput','Turn on both devices.')
        d.s.adb('reverse','--remove','tcp:8765');old=report().get('requestId')
        d.s.click('languageExecute');save('disconnected',wait_done(old),'ERROR',[False,False])
        d.s.adb('reverse','tcp:8765','tcp:8765')
        reset_fixture('normal',[True,True]);screen();set_text('languageInput','把灯和风扇都打开')
        old=report().get('requestId');d.s.click('languageExecute');save('already_at_goal',wait_done(old),'SUCCEEDED',[True,True])
    finally:
        d.s.adb('reverse','tcp:8765','tcp:8765')
        d.s.save(args.output/'summary.json',dict(completed=len(rows),passed=sum(r['passed'] for r in rows),rows=rows))
        screen()


if __name__=='__main__':main()
