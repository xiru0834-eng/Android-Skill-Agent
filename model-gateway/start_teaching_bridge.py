"""Reuse the phone's existing pairing without copying or logging API credentials."""
import os
import argparse
import xml.etree.ElementTree as ET
from intent_bridge import BridgeServer
from win_credentials import read_key
from workflow_experiment import adb

def resolve_selector(name):
    from skill_selection import select_skill
    from jev_selection import select_jev
    from selection_routing import select_routed
    from functools import partial
    if name in ('gpt','gpt-safe'):return select_skill
    if name=='jev':return select_jev
    if name=='routed':return partial(select_routed,compact=False)
    raise ValueError('UNKNOWN_SELECTOR')

def resolve_bounded_selector(name):
    from selection_deadline import select_bounded
    from deadline_remote import jev_remote
    if name in ('gpt','gpt-safe'):return lambda text,skills,budget:select_bounded('G',text,skills,budget)
    selector=resolve_selector(name)
    def bounded(text,skills,budget):
        budget.check()
        result=selector(text,skills,transport=lambda body:budget.call(jev_remote,body,'Jev'))
        budget.check()
        return result
    return bounded

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selector',choices=['gpt','gpt-safe','jev','routed'],default='gpt')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--max-calls',type=int,default=5)
    args=parser.parse_args()
    serial='R5CW134LLBZ'
    root=ET.fromstring(adb(serial,'shell','run-as','edu.sydney.probe','cat','shared_prefs/language_connection.xml'))
    token=next((n.text for n in root if n.get('name')=='pairing'),'')
    import re
    if not re.fullmatch('[a-f0-9]{48}',token):raise RuntimeError('Pair the phone first through Connection settings')
    os.environ['OPENAI_API_KEY']=read_key()
    selector=resolve_selector(args.selector)
    server=BridgeServer(('127.0.0.1',args.port),token,max_calls=args.max_calls,skill_selector=selector,
                       bounded_selector=resolve_bounded_selector(args.selector))
    adb(serial,'reverse','tcp:8765','tcp:'+str(args.port))
    print('Teaching bridge ready; USB only; selector='+args.selector+'; maximum '+str(args.max_calls)+' model calls per launch.',flush=True)
    try:server.serve_forever()
    finally:server.server_close()

if __name__=='__main__':main()
