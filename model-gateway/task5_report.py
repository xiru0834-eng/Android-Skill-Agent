"""Task5 host-only evidence E2E, preserved inputs and independent re-computation."""
import argparse
import json
from pathlib import Path
from task5_evidence import ReceiptReader, canonical, replay_verify
from task5_history import all_historical
from task5_protocol import paired_plan, paired_stats
from task5_counterexamples import experiment
from recovery_evidence import verify
from workflow_experiment import ROOT,write

PACKS={'S3':'normal-v39-batch2/S3-recording','M1':'normal-v39-batch3/M1-recording','M4':'normal-v39-batch3/M4-recording'}


def verify_bundle(folder):
    folder=Path(folder)
    if (folder/'integrity.json').exists():
        frozen=verify(folder)
        if not frozen['valid']:return dict(valid=False,phase='SEALED_BUNDLE_INTEGRITY',integrity=frozen)
    receipts=json.loads((folder/'input-receipts.json').read_text(encoding='utf-8'))
    integrity=replay_verify(folder/'inputs',receipts)
    if not integrity['valid']:return dict(valid=False,phase='INPUT_INTEGRITY',integrity=integrity)
    actual=all_historical(ReceiptReader(folder/'inputs'))
    original=json.loads((folder/'historical.json').read_text(encoding='utf-8'))
    return dict(valid=canonical(actual)==canonical(original),phase='FULL_RAW_RECOMPUTATION',files=integrity['files'],
        normalCompletion=actual['task3']['normalCompletion'],safeStops=actual['task3']['safeStops'],overall=actual['overall'])


def build(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    created=out.stat()
    try:
        return populate(out)
    except Exception as error:
        # Only this invocation's exclusively created directory may get a receipt.
        # Keep the original pipeline error even if receipt storage also fails.
        try:
            current=out.stat()
            if not out.is_symlink() and (created.st_dev,created.st_ino)==(current.st_dev,current.st_ino):
                with (out/'failure.json').open('x',encoding='utf-8') as stream:
                    json.dump(dict(phase='HOST_EVIDENCE_PIPELINE',error=type(error).__name__,reason=str(error)[:300]),stream)
        except OSError:
            pass
        raise


def populate(out):
    protections={f'task-{n}':verify(ROOT/f'output/autonomous-five/task-{n}') for n in [2,3,4]}
    write(out/'protected-before.json',protections)
    if not all(v['valid'] for v in protections.values()):raise ValueError('PRIOR_SEAL_CHANGED')
    reader=ReceiptReader(ROOT/'output');value=all_historical(reader)
    hashes={f:reader.read('autonomous-five/task-3/'+name+'/package.json')['skill']['traceSha256'] for f,name in PACKS.items()}
    plan=paired_plan(hashes);write(out/'paired-protocol.json',plan)
    write(out/'paired-ledger.json',[dict(c,arm=a,state='NOT_RUN',reason='ENVIRONMENT_AND_SOURCE_COORDINATES_NOT_READY') for c in plan['cases'] for a in c['order']])
    write(out/'paired-summary.json',paired_stats(plan,[]))
    write(out/'historical.json',value);write(out/'input-receipts.json',reader.receipts);reader.snapshot(out/'inputs')
    software=experiment();raw=software.pop('raw');write(out/'software-experiment.json',software)
    (out/'software-raw').mkdir()
    for key,data in raw.items():write(out/'software-raw'/f'{key}.json',data)
    replay=verify_bundle(out);write(out/'replication.json',replay)
    after={f'task-{n}':verify(ROOT/f'output/autonomous-five/task-{n}') for n in [2,3,4]};write(out/'protected-after.json',after)
    good=replay['valid'] and all(v['valid'] for v in after.values()) and software['matches']==software['n']
    result=dict(protocol='T5-EVIDENCE-1',softwarePipeline='PASS' if good else 'FAIL',overall='NOT_READY',newRemoteCalls=0,newDeviceInputs=0,
        evidenceFiles=len(reader.receipts),softwareCounterexamples=dict(n=software['n'],expectedMatches=software['matches']),
        androidComparison=dict(planned=72,executed=0,notRun=72),previousSealsUnchanged=all(v['valid'] for v in after.values()),
        pdfQA='NOT_RUN',fullRegression='NOT_RUN',candidateDeviceE2E='NOT_RUN')
    write(out/'summary.json',result);return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path);p.add_argument('--verify-bundle',type=Path);a=p.parse_args()
    if a.verify_bundle:
        result=verify_bundle(a.verify_bundle);print(json.dumps(result));return 0 if result['valid'] else 1
    parent=(ROOT/'output/autonomous-five/task-5').resolve()
    if a.output is None:p.error('NEW Task5 output required')
    target=a.output.resolve()
    if target==parent or not target.is_relative_to(parent) or target.exists():p.error('NEW Task5 output child required; existing evidence must not be overwritten')
    result=build(target)
    print(json.dumps(result));return 0 if result['softwarePipeline']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
