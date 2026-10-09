"""Evidence ledger retaining frozen Task 2 denominators and blocked transfer."""
import argparse
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from task2_protocol import plan,summarize,file_match
from task2_recompute import recompute
from workflow_experiment import write
from safe_probe_upgrade import adb_bytes
from workflow_contract import compile_evidence,WorkflowError


def negative_rows(rows):
    allowed={r['id'] for r in plan()['cases'] if r['group']=='negative'}
    known={row['id']:row for row in rows}
    if len(known)!=len(rows) or not set(known)<=allowed:raise ValueError('UNKNOWN_OR_DUPLICATE_NEGATIVE_RESULT')
    summarize(plan(),rows)  # Validate outcomes and required PASS facts before using them.
    return known


def recheck_negative(root,row):
    folder=root/'negatives-v36'/row['id']
    before=json.loads((folder/'before.json').read_text(encoding='utf-8'))
    after=json.loads((folder/'after.json').read_text(encoding='utf-8'))
    if before!=after or before.get('result')!=after.get('result'):raise ValueError('NEGATIVE_CHANGED_NATIVE_WORKFLOW_STATE')
    category=row['id'][2:].rsplit('-',1)[0]
    if category in ('empty','all_cancelled','unfinished_page'):
        trace=json.loads((folder/'trace.json').read_text(encoding='utf-8'))
        actions={'empty':[],'all_cancelled':['wfOpenLamp','wfLampValue80','wfLampCancel'],
                 'unfinished_page':['wfOpenLamp','wfLampValue80']}[category]
        if trace['end']!='STOPPED' or trace['source']!='AUTOMATED' or [s['id'] for s in trace['steps']]!=actions:
            raise ValueError('NEGATIVE_RECORDING_DIFFERS')
        try:compile_evidence(trace)
        except WorkflowError:pass
        else:raise ValueError('NEGATIVE_PRODUCED_VALID_SKILL')
        nodes=list(ET.parse(folder/'incomplete.xml').getroot().iter('node'))
        if not any(n.get('resource-id')=='edu.sydney.probe:id/teachStateTitle' and n.get('text')=='Recording ended · incomplete' for n in nodes):
            raise ValueError('NEGATIVE_UI_NOT_INCOMPLETE')
        if any(n.get('resource-id') in ('edu.sydney.probe:id/teachGenerate','edu.sydney.probe:id/teachSave') and n.get('enabled')=='true' for n in nodes):
            raise ValueError('NEGATIVE_UI_OFFERS_SAVE_OR_GENERATE')
    else:
        nodes=list(ET.parse(folder/'handled.xml').getroot().iter('node'));shown='\n'.join(n.get('text','') for n in nodes)
        if category=='invalid_save' and 'NAME_LENGTH' not in shown:raise ValueError('INVALID_SAVE_NOT_REPORTED')
        if category=='duplicate_name' and 'Not saved: duplicate name' not in shown:raise ValueError('DUPLICATE_NOT_REPORTED')
        if category not in ('invalid_save','duplicate_name','cancel_review'):raise ValueError('UNSUPPORTED_NEGATIVE_RECHECK')
    return True


def assemble(root,received):
    source=root/'emulator-journey-v36-r2';audit=recompute(source)
    preflight=json.loads((root/'phone-v34-preflight-refresh.json').read_text(encoding='utf-8'))
    if preflight['status']!='BLOCKED':raise ValueError('TRANSFER_ENVIRONMENT_CHANGED_REQUIRES_REASSESSMENT')
    negatives=json.loads((root/'negatives-v36'/'results.json').read_text(encoding='utf-8'))
    known=negative_rows(negatives)
    for row in negatives:
        if row['outcome']=='PASS':recheck_negative(root,row)
    ledger=[]
    for row in plan()['cases']:
        key=row['id']
        if row['group']=='teaching' and row['language']=='en':
            flow=row['flow'];record=audit['records'][flow];files=root/('files-v36-'+flow)
            exported=json.loads((files/'export-score.json').read_text(encoding='utf-8'))
            imported=json.loads((files/'import-score.json').read_text(encoding='utf-8'))
            pack=json.loads((files/'expected-package.json').read_text(encoding='utf-8'))
            named=json.loads((source/(flow+'-recording')/'named-package.json').read_text(encoding='utf-8'))
            approved=json.loads((source/(flow+'-recording')/'workflow-after.json').read_text(encoding='utf-8'))
            after=json.loads((files/'after.json').read_text(encoding='utf-8'))
            filename=json.loads((files/'file-protocol.json').read_text(encoding='utf-8'))['filename']
            blob=(files/filename).read_bytes()
            facts=dict(recordingExact=record['recordingExact'],guideExact=record['guideExact'],
                       savedPersistent=(json.loads(approved['approved'])==pack['skill'] and pack==named
                         and pack in json.loads(approved['library']) and pack in json.loads(after['library'])),
                       normalFilePath=(exported['normalPicker'] and imported['normalPicker'] and imported['reviewRequired']),
                       hashExact=(file_match(blob,received[flow]) and imported['byteHashExact']
                         and hashlib.sha256(blob).hexdigest()==exported['sha256'] and json.loads(blob)==named),
                       approvalIsolated=(imported['approvalIsolated'] and imported['reviewDidNotExecute']))
            ledger.append(dict(id=key,outcome='PASS' if all(v is True for v in facts.values()) else 'FAIL',
                               facts=facts,source='AUTOMATED',resumedObserverFailure=record['resumed'],
                               fileScope='same-device normal file chain, not transfer'))
        elif row['group']=='teaching':
            ledger.append(dict(id=key,outcome='BLOCKED',reason='TARGET_SERVICE_NOT_READY_AND_SOURCE_LIBRARY_CAPACITY_PRESERVED'))
        elif row['group']=='reuse':
            ledger.append(dict(id=key,outcome='BLOCKED',reason='APPLICATION_SERVICE_NOT_READY_ON_TARGET',
                               sourceEmulatorReplayIsNotTransfer=True))
        elif key in known:ledger.append(known[key])
        else:ledger.append(dict(id=key,outcome='NOT_RUN',reason='FULL_FROZEN_NATIVE_COUNTEREXAMPLE_NOT_RUN'))
    return dict(ledger=ledger,summary=summarize(plan(),ledger),sameDeviceReplay=dict(planned=27,scored=audit['scored'],
                 correct=audit['passed'],failed=audit['failed'],groups=audit['groups'],perRunDiskPersistence='NOT_CAPTURED'),
                firstObserverFailureRetained=True,paidCalls=0)


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);received={};receipts={}
    for flow in ('P','R','V'):
        folder=a.root/('files-v36-'+flow)
        filename=json.loads((folder/'file-protocol.json').read_text(encoding='utf-8'))['filename']
        if not re.fullmatch(r'named-workflow-[a-f0-9]{8}\.json',filename):raise ValueError('UNSAFE_EXPORT_FILENAME')
        blob=adb_bytes('emulator-5554','exec-out','cat','/sdcard/Download/'+filename)
        received[flow]=blob;(a.output/('received-'+filename)).write_bytes(blob)
        receipts[flow]=dict(filename=filename,bytes=len(blob),sha256=hashlib.sha256(blob).hexdigest(),
                            phase='POST_IMPORT_READBACK',device='emulator-5554',differentDevice=False)
    write(a.output/'file-receipts.json',receipts);value=assemble(a.root,received)
    write(a.output/'ledger.json',value['ledger']);write(a.output/'summary.json',{k:v for k,v in value.items() if k!='ledger'})
    print(json.dumps(value['summary']),flush=True)


if __name__=='__main__':main()
