"""Read-only re-score of one frozen normal and one fault batch. No score rewriting."""
import argparse
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from task3_protocol import cases,summary
from task3_audit import rejudge
from task3_faults import SPEC,safe_stop
from task3_fault_device import triggered
from workflow_experiment import write


def intervention_proven(fault,before,proof,nodes,result,case_id):
    try:
        if (before['result']['status']!='RUNNING' or before['result']['runId']!=result['runId']
                or before['oracle']['caseId']!=case_id
                or not any(e['kind'].startswith(('input:','edit:')) for e in before['oracle']['events'])):return False
        if fault=='foreground':return proof['kind']=='normal-system-Home' and any('com.google.android.apps.nexuslauncher' in line for line in proof['resumed'])
        found=[n for n in nodes if n.get('resource-id')=='edu.sydney.probe:id/teachOverlayFinish']
        if len(found)!=1 or found[0].get('text')!='Stop / return' or found[0].get('enabled')!='true':return False
        bounds=list(map(int,re.findall(r'-?\d+',found[0].get('bounds',''))))
        return proof['kind']=='normal-overlay-Stop' and bounds==proof['bounds'] and len(bounds)==4 and bounds[0]<bounds[2] and bounds[1]<bounds[3]
    except (KeyError,TypeError,ValueError):return False


def build(normal,faults,out):
    out.mkdir(parents=True,exist_ok=False);rows=[];detail=[];hashes={};plan={c['id']:c for c in cases()}
    def read(path):
        raw=path.read_bytes();hashes[str(path)]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
    for root in [normal,faults]:
        state=read(root/'source-stability.json')
        if state.get('sourceStable') is not True:raise ValueError('SOURCE_NOT_FROZEN')
        for case_file in sorted(root.rglob('case.json')):
            case=read(case_file);where=case_file.parent;key=case['id']
            if key not in plan:raise ValueError('UNPLANNED_CASE')
            if not (where/'result.json').exists():
                rows.append(dict(id=key,status='NOT_RUN',evidenceQualified=False,reason='PREPARATION_DID_NOT_START_PROVEN_RUN'));continue
            try:
                d={name:read(where/(name+'.json')) for name in ['skill','result','oracle','journal','delayed-audits','disk','before']}
                arguments=[d['skill'],case['initial'],d['result'],d['oracle'],d['journal'],d['delayed-audits'],d['disk'],case['caseId']]
                if case['group'] in ['single','multi','challenge']:
                    checked=rejudge(*arguments);trigger=True
                    if case['group']=='challenge':trigger=any(e['kind']==('save_pending' if case['fault']=='delay' else 'navigation_pending') for e in d['oracle']['events'])
                    okay=checked['correctCompletion']
                else:
                    fault=case['fault'];ui=None;intervention=False
                    if fault in ['missing','duplicate']:
                        ui=ET.Element('hierarchy')
                        for n in read(where/'fault-tree.json'):ET.SubElement(ui,'node',n)
                    if fault in ['cancel','foreground'] and (where/'intervention.json').exists():
                        overlay=read(where/'intervention-overlay.json') if fault=='cancel' else []
                        intervention=intervention_proven(fault,read(where/'intervention-before.json'),read(where/'intervention.json'),overlay,d['result'],case['caseId'])
                    trigger=triggered(fault,d['before'],d['result'],d['oracle'],ui,intervention)
                    checked=safe_stop(fault,*arguments,trigger);okay=checked['safeStop']
                value=dict(id=key,status='NOT_TRIGGERED' if not trigger else ('PASS' if okay else ('FAIL' if checked['evidenceQualified'] else 'UNVERIFIED')),
                    evidenceQualified=checked['evidenceQualified'] and trigger,elapsedMs=checked['elapsedMs'],falseSuccess=checked['falseSuccess'])
                rows.append(value);detail.append(dict(case=case,source=str(where),score=checked,triggered=trigger,
                    inputs=len(d['result']['actions']),skips=sum(e['kind']=='SKIP_ALREADY_AT_TARGET' for e in d['journal']),profile=d['result'].get('profilePrefix',{})))
            except (FileNotFoundError,KeyError,TypeError,ValueError,IndexError) as error:
                rows.append(dict(id=key,status='UNVERIFIED',evidenceQualified=False,reason='RAW_EVIDENCE_INCOMPLETE:'+type(error).__name__))
        seen={r['id'] for r in rows}
        for row in read(root/'rows.json'):
            if row['id'] in seen:continue
            if row['status']=='BLOCKED':
                if plan[row['id']].get('flow')!='S6' or row['reason']!='S6_SOURCE_SAVE_AMBIGUOUS_WITHOUT_STATE_CHANGE':raise ValueError('UNKNOWN_CAPTURE_BLOCK')
                trace=read(Path(row['sourceFailure']))
                if trace['end']!='REJECTED' or not trace['error']:raise ValueError('CAPTURE_BLOCK_NOT_PROVEN')
                rows.append(row)
            elif row['status']=='NOT_RUN':rows.append(row)
            else:raise ValueError('CAPTURE_CLAIM_WITHOUT_RAW_CASE')
    totals=summary(rows);latency={};by_flow={}
    for group in ['single','multi','fault','challenge']:
        values=sorted(r['elapsedMs'] for r in rows if plan[r['id']]['group']==group and r['status']=='PASS')
        latency[group]=dict(n=len(values),p50Ms=values[math.ceil(.5*len(values))-1] if values else None,p95Ms=values[math.ceil(.95*len(values))-1] if values else None)
    for flow in [c['flow'] for c in cases() if c['group'] in ['single','multi']]:
        slots=[c for c in cases() if c.get('flow')==flow];found=[r for r in rows if plan[r['id']].get('flow')==flow]
        by_flow[flow]=dict(planned=len(slots),passed=sum(r['status']=='PASS' for r in found),started=sum('elapsedMs' in r for r in found))
    totals.update(latency=latency,byFlow=by_flow,falseSuccess=sum(r.get('falseSuccess',False) for r in rows),
        sourceBatches=[str(normal),str(faults)],independentRawReaudit=True)
    write(out/'summary.json',totals);write(out/'rows.json',rows);write(out/'detail.json',detail);write(out/'raw-hashes.json',hashes)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--normal',type=Path,required=True);p.add_argument('--faults',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();build(a.normal,a.faults,a.output)
