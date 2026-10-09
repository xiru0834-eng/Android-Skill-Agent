"""Explicit local developer CLI. Native capture/navigation always blocked."""
import argparse
import json
from pathlib import Path

from interaction_trace import native_readiness
from trace_contract import TraceError
from historical_trace import import_catalog_material
from trace_store import TraceStore

def fixture_demo():
    # Explicit synthetic channel only. No fixtures imported by trace/session/store modules.
    from test_support import Harness, action, receipt, write_audit
    from test_session import session
    h=Harness();s=session(h)
    a,b,c=h.observe('home'),h.observe('details'),h.observe('info')
    s.record_interaction('HUMAN_DEMONSTRATION',a,b,action(),receipt(a,b,status='OBSERVED_INPUT_SIMULATED'),
                         write_audit(),expected_target=h.target(b))
    s.record_interaction('HUMAN_DEMONSTRATION',b,c,action(),receipt(b,c,status='OBSERVED_INPUT_SIMULATED'),
                         write_audit(),expected_target=h.target(c))
    h.world.page='home'
    result=s.navigate_known(h.world,h.target(c))
    return {'kind':'ControlledFixtureDemo','channel':'OFFLINE_CONTROLLED_TRAJECTORY',
            'navigation':result,'bundle':s.bundle(),'real_android':False,'paid_model_requests':0}

def main():
    p=argparse.ArgumentParser(description='P2.3 local evidence only; never ADB or paid models')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('native-status')
    h=sub.add_parser('historical');h.add_argument('source_id')
    d=sub.add_parser('fixture-demo');d.add_argument('--store',type=Path)
    r=sub.add_parser('read');r.add_argument('store',type=Path);r.add_argument('trace_id')
    args=p.parse_args()
    try:
        if args.command=='native-status':result=native_readiness()
        elif args.command=='historical':result=import_catalog_material(args.source_id)
        elif args.command=='read':
            with TraceStore(args.store,read_only=True) as db:result=db.read(args.trace_id)
        else:
            result=fixture_demo()
            if args.store:
                with TraceStore(args.store) as db:
                    result['storage_receipt']=db.append(result['bundle'],expected_revision=db.revision())
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
        return 0
    except (TraceError,ValueError) as error:
        print(json.dumps({'status':'REJECTED','code':getattr(error,'code','LOCAL_PROTOCOL_ERROR'),
                          'execution_authority':False},sort_keys=True))
        return 2

if __name__=='__main__':
    raise SystemExit(main())
