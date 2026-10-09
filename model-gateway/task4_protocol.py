"""Frozen original-package transfer matrix; no device calls or approval creation."""
import collections
import hashlib
import json
import math
import re
from pathlib import Path
from workflow_contract import compile_evidence,canonical
from task3_protocol import FLOWS,INITIALS

ROOT=Path(__file__).resolve().parents[1]
SOURCES={
    'S3':'output/autonomous-five/task-3/normal-v39-batch2/S3-recording',
    'M1':'output/autonomous-five/task-3/normal-v39-batch3/M1-recording',
    'M4':'output/autonomous-five/task-3/normal-v39-batch3/M4-recording',
}
DISPLAYS={'D0':([720,1280],240,1.0),'D1':([540,960],240,1.0),
          'D2':([1080,1920],320,1.0),'D3':([720,1280],240,1.3)}
STATUS=('PASS','FAIL','BLOCKED','NOT_RUN','UNVERIFIED','NOT_TRIGGERED')


def cases():
    rows=[dict(id='chain-'+flow,group='chain',flow=flow) for flow in SOURCES]
    for display in DISPLAYS:
        for appearance in ('native','reordered'):
            for flow in SOURCES:
                for i in range(3):
                    for repeat in range(3):
                        rows.append(dict(id=f'{display}-{appearance}-{flow}-i{i}-r{repeat}',group='normal',
                            display=display,appearance=appearance,flow=flow,initial=INITIALS[i][:],initialIndex=i,repeat=repeat))
    for fault in ('missing','duplicate'):
        for flow in SOURCES:
            for repeat in range(3):
                rows.append(dict(id=f'F-{fault}-{flow}-r{repeat}',group='negative',display='D0',appearance='native',
                    flow=flow,initial=INITIALS[0][:],fault=fault,repeat=repeat))
    return rows


def summarize(observations):
    plan={row['id']:row for row in cases()};seen={}
    for row in observations:
        key=row.get('id');status=row.get('status')
        if key not in plan or key in seen or status not in STATUS:raise ValueError('UNKNOWN_DUPLICATE_OR_INVALID_CASE')
        if status=='PASS' and row.get('evidenceQualified') is not True:raise ValueError('PASS_WITHOUT_EVIDENCE')
        seen[key]=row
    groups={}
    for group in ('chain','normal','negative'):
        slots=[r for r in plan.values() if r['group']==group]
        counts=collections.Counter(seen.get(r['id'],{}).get('status','NOT_RUN') for r in slots)
        groups[group]=dict(planned=len(slots),**{s:counts[s] for s in STATUS})
    return dict(protocol='T4-TRANSFER-1',groups=groups,
        transferValidation='PASS' if all(g['PASS']==g['planned'] for g in groups.values()) else 'NOT_READY',
        overall='NOT_READY',prerequisiteTask3='NOT_READY',paidCalls=0)


def source_record(flow):
    folder=ROOT/SOURCES[flow]
    trace=json.loads((folder/'trace.json').read_text(encoding='utf-8'))
    skill=json.loads((folder/'skill.json').read_text(encoding='utf-8'))
    package=json.loads((folder/'package.json').read_text(encoding='utf-8'))
    if (canonical(compile_evidence(trace))!=canonical(skill) or canonical(package['skill'])!=canonical(skill) or trace['source']!='AUTOMATED'
        or [s['id'] for s in skill['steps']]!=FLOWS[flow]['actions']):raise ValueError('SOURCE_RECORDING_DIFFERS')
    package_bytes(canonical(package).encode('utf-8'),package)
    return dict(flow=flow,source=str(folder.relative_to(ROOT)),trace=trace,skill=skill,package=package)


def package_bytes(blob,expected):
    if type(blob) is not bytes or not 0<len(blob)<=262144:raise ValueError('FILE_SIZE')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('DUPLICATE_JSON_KEY')
            result[key]=value
        return result
    def constant(value):raise ValueError('NON_FINITE_JSON')
    try:pack=json.loads(blob.decode('utf-8','strict'),object_pairs_hook=pairs,parse_constant=constant)
    except (UnicodeDecodeError,json.JSONDecodeError) as error:raise ValueError('INVALID_FILE_ENCODING_OR_JSON') from error
    if (type(pack) is not dict or set(pack)!={'kind','version','name','skill'} or pack['kind']!='NAMED_WORKFLOW'
        or type(pack['version']) is not int or pack['version']!=1 or canonical(pack)!=canonical(expected)):
        raise ValueError('ORIGINAL_PACKAGE_DIFFERS')
    return pack


def fingerprint(blob):return hashlib.sha256(blob).hexdigest()


def display_state(size,density,font):
    def parse(raw,field,convert):
        physical=re.findall(r'^Physical '+field+r': (.+)$',raw.strip(),re.M)
        override=re.findall(r'^Override '+field+r': (.+)$',raw.strip(),re.M)
        if len(physical)!=1 or len(override)>1:raise ValueError('DISPLAY_FORMAT')
        return convert(physical[0]),convert(override[0]) if override else None
    def dimensions(value):
        if not re.fullmatch(r'[1-9]\d*x[1-9]\d*',value):raise ValueError('DISPLAY_SIZE')
        return list(map(int,value.split('x')))
    def dpi(value):
        if not re.fullmatch(r'[1-9]\d*',value):raise ValueError('DISPLAY_DENSITY')
        return int(value)
    physical,override=parse(size,'size',dimensions);physical_dpi,override_dpi=parse(density,'density',dpi)
    try:scale=None if font.strip()=='null' else float(font.strip())
    except ValueError as error:raise ValueError('FONT_SCALE') from error
    if scale is not None and (not math.isfinite(scale) or scale<=0):raise ValueError('FONT_SCALE')
    return dict(physicalSize=physical,overrideSize=override,physicalDensity=physical_dpi,overrideDensity=override_dpi,
        effectiveSize=override or physical,effectiveDensity=override_dpi or physical_dpi,fontScale=scale,fontRaw=font.strip())


def display_matches(label,state):
    size,density,font=DISPLAYS[label]
    return state['effectiveSize']==size and state['effectiveDensity']==density and state['fontScale']==font
