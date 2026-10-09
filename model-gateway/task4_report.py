"""Recompute raw evidence. Scores supplied by the capture process are never authority."""
import argparse
import hashlib
import json
import math
import re
import struct
import xml.etree.ElementTree as ET
from pathlib import Path
from workflow_experiment import ROOT,write
from task4_protocol import cases,source_record,summarize,canonical,display_state,display_matches,DISPLAYS
from task4_files import load_chain,ARTIFACTS
from task4_transfer import chain_check,fault_score
from task3_audit import rejudge


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def device_valid(value,avd):
    expected={p:dict(version=v,apkSha256=hashlib.sha256((ROOT/a).read_bytes()).hexdigest()) for p,(v,a) in ARTIFACTS.items()}
    return value.get('avd')==avd and value.get('serial')=='emulator-5554' and value.get('artifacts')==expected


def condition_valid(folder,row,before,oracle,skill):
    display=read(folder/'display.json');actual=display_state(**display['raw'])
    png=(folder/'fixture-public.png').read_bytes()
    if png[:8]!=b'\x89PNG\r\n\x1a\n':return False
    dimensions=list(struct.unpack('>II',png[16:24]));ui=ET.parse(folder/'fixture-public.xml').getroot()
    windows=list(ui)
    if len(windows)!=1:return False
    bounds=list(map(int,re.findall(r'-?\d+',windows[0].get('bounds',''))))
    return (display_matches(row['display'],actual) and display['state']==actual and dimensions==DISPLAYS[row['display']][0]
        and display['pngDimensions']==dimensions and len(bounds)==4 and [bounds[2]-bounds[0],bounds[3]-bounds[1]]==dimensions
        and all(o['appearance']==row['appearance'] and o['fault']==row.get('fault','normal') and o['initial']==row['initial']
                and o['layout']==('single' if skill['startPage']=='single' else 'multi') for o in [before,oracle]))


def score_case(folder,row):
    base=dict(id=row['id'],evidenceQualified=False,falseSuccess=False)
    if not folder.exists():return dict(base,status='NOT_RUN')
    if (folder/'failure.json').exists() and not (folder/'result.json').exists():return dict(base,status='BLOCKED',reason=read(folder/'failure.json').get('reason'))
    try:
        case=read(folder/'case.json')
        if {k:v for k,v in case.items() if k!='caseId'}!=row:raise ValueError('CASE_DIFFERS_FROM_FROZEN_SLOT')
        record=source_record(row['flow']);skill=read(folder/'skill.json')
        if canonical(skill)!=canonical(record['skill']):raise ValueError('ORIGINAL_SKILL_CHANGED')
        if not device_valid(read(folder/'device.json'),'Task4Transfer'):raise ValueError('DEVICE_ARTIFACT_IDENTITY')
        before=read(folder/'before.json');result=read(folder/'result.json');oracle=read(folder/'oracle.json')
        if before['caseId']!=case['caseId'] or oracle['caseId']!=case['caseId']:raise ValueError('FIXTURE_IDENTITY')
        if not condition_valid(folder,row,before,oracle,skill):raise ValueError('ACTUAL_CONDITION_UNPROVEN')
        if result['runId']==read(folder/'previous.json')['previousRun']:raise ValueError('PREVIOUS_RESULT_REUSED')
        args=[skill,row['initial'],result,oracle,read(folder/'journal.json'),read(folder/'delayed-audits.json'),read(folder/'disk.json'),case['caseId']]
        score=(fault_score(row,*args,ET.parse(folder/'terminal-public.xml').getroot()) if row['group']=='negative' else rejudge(*args))
        okay=score.get('safeStop',score.get('correctCompletion',False))
        return dict(base,status='PASS' if okay else ('FAIL' if score['evidenceQualified'] else 'UNVERIFIED'),
            evidenceQualified=score['evidenceQualified'],falseSuccess=score['falseSuccess'],elapsedMs=score['elapsedMs'],
            errors=score['errors'],inputs=len(result['actions']),runId=result['runId'])
    except (OSError,KeyError,TypeError,ValueError,IndexError,ET.ParseError,struct.error) as error:
        return dict(base,status='UNVERIFIED',reason=str(error))


def audit(source,receiver,runs,out):
    out.mkdir(parents=True,exist_ok=False);rows=[]
    for row in cases():
        if row['group']!='chain':rows.append(score_case(runs/row['id'],row));continue
        flow=row['flow'];target=receiver/flow;original=source/flow
        base=dict(id=row['id'],evidenceQualified=False)
        try:
            if not target.exists():
                blocked=(source/'failure.json').exists() or (receiver/'failure.json').exists()
                rows.append(dict(base,status='BLOCKED' if blocked else 'NOT_RUN'));continue
            proof=load_chain(original,target);checked=chain_check(source_record(flow)['package'],proof)
            valid=(checked['correctChain'] and device_valid(read(original/'device.json'),'Task3Workflows')
                and device_valid(read(target/'device.json'),'Task4Transfer')
                and read(source/'source-stability.json')['sourceStable'] is True and read(receiver/'source-stability.json')['sourceStable'] is True)
            rows.append(dict(base,status='PASS' if valid else 'UNVERIFIED',evidenceQualified=valid,errors=checked['errors']))
        except (OSError,KeyError,TypeError,ValueError,ET.ParseError) as error:rows.append(dict(base,status='UNVERIFIED',reason=str(error)))
    result=summarize(rows);latency={}
    for label in DISPLAYS:
        values=sorted(r['elapsedMs'] for r in rows if r['id'].startswith(label+'-') and r['status']=='PASS')
        latency[label]=dict(n=len(values),P50=values[math.ceil(.5*len(values))-1] if values else None,
            P95=values[math.ceil(.95*len(values))-1] if values else None,max=max(values) if values else None)
    result.update(latency=latency,falseSuccess=sum(r.get('falseSuccess',False) for r in rows),
        started=sum((runs/r['id']/'case.json').exists() for r in cases() if r['group']!='chain'),
        actualTerminalRecords=sum((runs/r['id']/'result.json').exists() for r in cases() if r['group']!='chain'),
        settingRestored=read(runs/'restoration.json').get('restored') if (runs/'restoration.json').exists() else None)
    gates={}
    for name,root in [('sourceStable',source),('receiverStable',receiver),('executionStable',runs)]:
        gates[name]=(read(root/'source-stability.json').get('sourceStable') is True) if (root/'source-stability.json').exists() else False
    try:
        original=display_state(**read(runs/'display-before.json')['raw']);restored=display_state(**read(runs/'display-after.json')['raw'])
        gates['displayRestored']=original==restored
        before=read(runs/'preferences-before.json');after=read(runs/'preferences-after.json')
        gates['libraryPreserved']=canonical(json.loads(before.get('library','[]')))==canonical(json.loads(after.get('library','[]')))
    except (OSError,KeyError,TypeError,ValueError):gates.update(displayRestored=False,libraryPreserved=False)
    result['gates']=gates
    if result['settingRestored'] is not True or not all(gates.values()):result['transferValidation']='NOT_READY'
    result.update(softwareValidation='NOT_READY',legacyDeviceE2E='NOT_RUN',fullRegression='REPORTED_SEPARATELY')
    write(out/'rows.json',rows);write(out/'summary.json',result)
    evidence={}
    for root in [source,receiver,runs]:
        if not root.exists():continue
        for p in sorted(root.rglob('*')):
            if p.is_file():evidence[str(p.resolve())]=hashlib.sha256(p.read_bytes()).hexdigest()
    write(out/'raw-hashes.json',evidence);return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--receiver',type=Path,required=True)
    p.add_argument('--runs',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if not a.output.resolve().is_relative_to(ROOT/'output/autonomous-five/task-4'):p.error('NEW Task 4 output required')
    print(json.dumps(audit(a.source,a.receiver,a.runs,a.output)))
