"""Fixed supported Android fault/challenge rows; UI controls, no private approval writes."""
import argparse
import base64
import hashlib
import json
import re
import time
import xml.etree.ElementTree as ET
from pathlib import Path
import task3_device_checks as device
from task3_protocol import cases,summary,judge
from task3_faults import SPEC,safe_stop
from task3_audit import rejudge
from workflow_experiment import write


def interrupted(fault,previous,out):
    until=time.monotonic()+12
    while time.monotonic()<until:
        r=device.private(device.SERIAL,device.PROBE,'recorded-workflow-result.json')
        if r.get('runId')!=previous and r.get('status')=='RUNNING':
            oracle=device.private(device.SERIAL,device.APP,'workflow-oracle.json')
            if any(e['kind'].startswith(('input:','edit:')) for e in oracle['events']):break
        if r.get('runId')!=previous and r.get('status') in ['SUCCEEDED','UNCONFIRMED','CANCELLED']:return False
        time.sleep(.1)
    else:return False
    write(out/'intervention-before.json',dict(result=r,oracle=oracle))
    if fault=='foreground':
        device.adb(device.SERIAL,'shell','input','keyevent','3')
        dump=device.adb(device.SERIAL,'shell','dumpsys','activity','activities')
        resumed=[line.strip() for line in dump.splitlines() if 'mResumedActivity' in line or 'topResumedActivity' in line]
        write(out/'intervention.json',dict(kind='normal-system-Home',resumed=resumed))
        return bool(resumed) and any('com.google.android.apps.nexuslauncher' in line for line in resumed)
    raw=device.adb(device.SERIAL,'shell','am','instrument','-w','-e','probeOverlay','true','edu.sydney.evaluation/.Observer')
    found=re.search(r'INSTRUMENTATION_RESULT: xml=(\S+)',raw)
    if not found:return False
    ui=ET.fromstring(base64.b64decode(found[1]));write(out/'intervention-overlay.json',[dict(n.attrib) for n in ui.iter('node')])
    nodes=[n for n in ui.iter('node') if n.get('resource-id')==device.PROBE+':id/teachOverlayFinish']
    if len(nodes)!=1 or nodes[0].get('text')!='Stop / return':return False
    b=list(map(int,re.findall(r'-?\d+',nodes[0].get('bounds',''))))
    if len(b)!=4 or b[2]<=b[0] or b[3]<=b[1] or nodes[0].get('enabled')!='true':return False
    write(out/'intervention.json',dict(kind='normal-overlay-Stop',bounds=b))
    device.adb(device.SERIAL,'shell','input','tap',(b[0]+b[2])//2,(b[1]+b[3])//2)
    return True


def triggered(fault,before,result,oracle,ui,intervention):
    kinds=[e['kind'] for e in oracle['events']]
    nodes=list(ui.iter('node')) if ui is not None else []
    if fault=='missing':return before['fault']=='missing' and not any(n.get('resource-id')==device.APP+':id/wfFanSave' for n in nodes) and result['reason']=='MISSING:wfFanSave'
    if fault=='duplicate':return before['fault']=='duplicate' and sum(n.get('resource-id')==device.APP+':id/wfLampPower' for n in nodes)==2
    if fault=='wrong_page':return before['events'][-1]['page']=='lamp'
    if fault=='save_drop':return 'dropped_save' in kinds
    if fault=='late':return 'control_loading' in kinds and 'control_available' in kinds and result['finishedMs']<next(e['ms'] for e in oracle['events'] if e['kind']=='control_available')
    if fault=='rollback':return any(e['kind']=='save' and e['saved'][:2]==before['initial'][:2] and e['saved'][2:]==[1,1] for e in oracle['events'])
    return intervention


def run(skills,out):
    out.mkdir(parents=True,exist_ok=False);write(out/'device.json',device.gate())
    source=device.source_hashes();source[__file__]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    extra=[Path(__file__).with_name(n) for n in ['task3_faults.py','task3_audit.py']]
    source.update({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in extra})
    write(out/'source-hashes.json',source)
    plan=[c for c in cases() if c['group'] in ['fault','challenge']];write(out/'frozen-cases.json',plan);rows=[]
    try:
        for row in plan:
            fault=row['fault'];where=out/row['id'];where.mkdir()
            if row['group']=='fault' and fault not in SPEC:
                value=dict(id=row['id'],status='NOT_RUN',evidenceQualified=False,reason='NO_FAITHFUL_DEVICE_INJECTOR')
                rows.append(value);write(where/'score.json',value);write(out/'rows.json',rows);continue
            flow=SPEC[fault]['flow'] if fault in SPEC else 'M1';skill=skills[flow];initial=[0,40,0,3]
            case_id,before=device.fixture(skill,initial,SPEC[fault]['fixture'] if fault in SPEC else fault,wrong=fault=='wrong_page')
            write(where/'before.json',before);write(where/'case.json',dict(row,flow=flow,initial=initial,caseId=case_id))
            previous=device.private(device.SERIAL,device.PROBE,'recorded-workflow-result.json')['runId']
            device.start_run(skill);intervention=interrupted(fault,previous,where) if fault in ['cancel','foreground'] else False
            result,oracle,journal,audits,disk=device.collect(skill,initial,case_id,where,previous)
            if row['group']=='challenge':
                trigger=any(e['kind']==('save_pending' if fault=='delay' else 'navigation_pending') for e in oracle['events'])
                checked=rejudge(skill,initial,result,oracle,journal,audits,disk,case_id)
                okay=trigger and checked['correctCompletion']
            else:
                ui=None
                if fault in ['missing','duplicate']:
                    ui=device.tree(device.SERIAL);device.snap(device.SERIAL,where/'fault-window.png')
                    write(where/'fault-tree.json',[dict(n.attrib) for n in ui.iter('node')])
                trigger=triggered(fault,before,result,oracle,ui,intervention)
                checked=safe_stop(fault,skill,initial,result,oracle,journal,audits,disk,case_id,trigger);okay=checked['safeStop']
            write(where/'score.json',dict(checked,triggered=trigger))
            value=dict(id=row['id'],status='NOT_TRIGGERED' if not trigger else ('PASS' if okay else ('FAIL' if checked['evidenceQualified'] else 'UNVERIFIED')),
                       evidenceQualified=checked['evidenceQualified'] and trigger,elapsedMs=checked['elapsedMs'],falseSuccess=checked['falseSuccess'])
            rows.append(value);write(out/'rows.json',rows);write(out/'summary.json',summary(rows));print(row['id']+' '+value['status'],flush=True)
            if value['status'] not in ['PASS','NOT_TRIGGERED']:raise RuntimeError('FAULT_CONFIRMATION_NOT_CORRECT')
    except Exception as error:
        write(out/'failure.json',dict(error=type(error).__name__,reason=str(error),paidCalls=0));raise
    finally:
        expected=device.source_hashes();expected[__file__]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        expected.update({str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in extra})
        write(out/'source-stability.json',dict(sourceStable=expected==source));write(out/'preparation-reads.json',device.PREPARATION_READS)
        write(out/'summary.json',summary(rows))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--skills',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();run(json.loads(a.skills.read_text(encoding='utf-8')),a.output)
