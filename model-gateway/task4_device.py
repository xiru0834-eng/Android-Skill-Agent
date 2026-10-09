"""Scoped Task 4 capture CLI; fresh output directories, no rerecording or API calls."""
import argparse
import hashlib
import json
from pathlib import Path
from workflow_experiment import ROOT,write
from task4_protocol import SOURCES,cases
from task4_files import gate,export_one,receive_one,snapshot
from task3_device_checks import source_hashes,SERIAL,PREPARATION_READS


def hashes():
    result=source_hashes()
    files=list((ROOT/'model-gateway').glob('task4_*.py'))+list((ROOT/'model-gateway').glob('test_task4_*.py'))
    files+=[ROOT/'tasks/autonomous-five/task-4-data-protocol.md',ROOT/'model-gateway/task3_audit.py']
    result.update({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['export','receive','confirm'])
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--source',type=Path)
    parser.add_argument('--development',action='store_true');args=parser.parse_args()
    out=args.output.resolve()
    if not out.is_relative_to(ROOT/'output/autonomous-five/task-4') or out.exists():parser.error('NEW Task 4 directory required')
    if args.mode!='export' and args.source is None:parser.error('Original source export directory required')
    out.mkdir(parents=True);frozen=hashes();write(out/'source-hashes.json',frozen)
    write(out/'planned-cases.json',cases());rows=[];where=out
    try:
        write(out/'device.json',gate('Task3Workflows' if args.mode=='export' else 'Task4Transfer'))
        if args.mode=='confirm':
            from task4_execution import confirm
            confirm(args.source,out,development=args.development);return 0
        for flow in SOURCES:
            where=out/flow
            export_one(flow,where) if args.mode=='export' else receive_one(flow,args.source,where)
            rows.append(dict(flow=flow,stage=args.mode,status='PASS',paidCalls=0));write(out/'stage-rows.json',rows)
        return 0
    except Exception as error:
        if where!=out:write(where/'failure.json',dict(stage=args.mode,reason=str(error),error=type(error).__name__,paidCalls=0))
        write(out/'failure.json',dict(stage=args.mode,flow=where.name if where!=out else None,reason=str(error),error=type(error).__name__,paidCalls=0))
        try:snapshot(where,'failure')
        except Exception:pass
        print('STOP '+args.mode+': '+str(error),flush=True);return 1
    finally:
        write(out/'preparation-reads.json',PREPARATION_READS)
        current=hashes();write(out/'source-stability.json',dict(sourceStable=current==frozen,paidCalls=0));write(out/'current-source-hashes.json',current)


if __name__=='__main__':raise SystemExit(main())
