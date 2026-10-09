"""Retrospective adapters reuse original judges; receipt snapshots are relocatable."""
import tempfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from task5_evidence import canonical, received_language, judge_run
from task5_protocol import latency, stable_repeats
from evaluation_framework import ratio
from task2_result_bundle import assemble
from task3_protocol import cases as task3_cases, summary as task3_summary
from task3_protocol import INITIALS
from task3_faults import SPEC
from task3_faults import safe_stop
from task3_fault_device import triggered
from task3_report import intervention_proven
from task4_protocol import cases as task4_cases, summarize as task4_summary

T1='first-step-closeout/gpt-actual-catalog-v33'
T2='autonomous-five/task-2'
T3='autonomous-five/task-3'
T4='autonomous-five/task-4'


def evidence_summary(rows):
    states=['PASS','FAIL','BLOCKED','NOT_RUN','UNVERIFIED','NOT_TRIGGERED']
    if len({r['id'] for r in rows})!=len(rows) or any(r['state'] not in states for r in rows):raise ValueError('LEDGER_ID_OR_STATE')
    counts=Counter(r['state'] for r in rows);scored=counts['PASS']+counts['FAIL']
    return dict(planned=len(rows),states={s:counts[s] for s in states},passScored=ratio(counts['PASS'],scored),
        passPlanned=ratio(counts['PASS'],len(rows)),scorable=ratio(scored,len(rows)),
        latencyAll=latency([r['elapsedMs'] for r in rows if r.get('elapsedMs') is not None],len(rows)),
        latencyPass=latency([r['elapsedMs'] for r in rows if r['state']=='PASS' and r.get('elapsedMs') is not None],counts['PASS']),
        latencyFail=latency([r['elapsedMs'] for r in rows if r['state']=='FAIL' and r.get('elapsedMs') is not None],counts['FAIL']))


def collect_tree(reader,name):
    root=reader.path(name)
    if not root.exists():return
    for p in sorted(root.rglob('*')):
        if p.is_symlink():raise ValueError('LINK_NOT_ALLOWED')
        if p.is_file() and p.suffix in ['.json','.xml','.txt']:reader.raw(p.relative_to(reader.root).as_posix())


def remote_identity(response,seen):
    key=response.get('request_id')
    if not isinstance(key,str) or not key or key in seen:raise ValueError('MISSING_OR_DUPLICATE_RESPONSE_ID')
    seen.add(key)


def task1_language(reader):
    p=reader.read(T1+'/protocol.json');rows=[];seen=set();responses=set()
    if len(p['cases'])!=60 or len(p['trials'])!=180 or p['selectionOnly'] is not True:raise ValueError('LANGUAGE_PROTOCOL')
    for i,trial in enumerate(p['trials']):
        case=p['cases'][trial['index']];repeat=trial['repeat'];key=(case['caseId'],repeat)
        if key in seen or type(repeat) is not int or repeat not in [0,1,2]:raise ValueError('LANGUAGE_DUPLICATE_TRIAL')
        seen.add(key);prefix=f'{T1}/trials/{i:03d}'
        try:
            row=reader.read(prefix+'/row.json');req=reader.read(prefix+'/request-1.json');resp=reader.read(prefix+'/response-1.json')
            remote_identity(resp,responses)
            checked=received_language(case,row,req,resp,p['model'],p['sharedBudgetSeconds'])
            if row.get('repeat')!=repeat:checked.update(qualified=False,correct=False,errors=['REPEAT_DIFFERS'])
            state='PASS' if checked['correct'] else ('FAIL' if checked['qualified'] else 'UNVERIFIED')
            elapsed=row.get('ms') if checked['qualified'] else None
        except (OSError,ValueError):checked=dict(qualified=False,correct=False,errors=['MISSING_OR_INVALID_RECORD']);state='UNVERIFIED';elapsed=None
        rows.append(dict(id=case['caseId']+f'-r{repeat}',state=state,positive=case['expected'] is not None,
            language=case['language'],family=case['caseId'],repeat=repeat,elapsedMs=elapsed,checked=checked,source=prefix))
    ledger=reader.read(T1+'/paid-ledger.json')
    return dict(rows=rows,summary=evidence_summary(rows),groups={language:evidence_summary([r for r in rows if r['language']==language]) for language in ['zh','en']},
        positive=evidence_summary([r for r in rows if r['positive']]),negative=evidence_summary([r for r in rows if not r['positive']]),
        stability=stable_repeats([(r['family'],r['repeat'],r['state']=='PASS') for r in rows]),
        historicalPaidLedger=dict(attempts=ledger['attempts'],settledNanoUsd=sum(r['nanoUsd'] for r in ledger['rows'] if r['state']=='SETTLED'),
            actualInvoiceVerified=False,currentPricingVerified=False),model=p['model'],newRemoteCalls=0,
        phase='historical-confirmation-v33',scope='Language selection only; author-labelled expressions, not independent user gold')


def task2_original(reader):
    for name in ['emulator-journey-v36-r2','negatives-v36',*['files-v36-'+f for f in ['P','R','V']]]:collect_tree(reader,T2+'/'+name)
    reader.read(T2+'/phone-v34-preflight-refresh.json');received={}
    for f in ['P','R','V']:
        filename=reader.read(T2+'/files-v36-'+f+'/file-protocol.json')['filename']
        received[f]=reader.raw(T2+'/final-ledger-v36/received-'+filename)
    # Original auditor runs against received bytes, not a connected phone.
    with tempfile.TemporaryDirectory() as tmp:
        reader.snapshot(Path(tmp)/'inputs');value=assemble(Path(tmp)/'inputs'/T2,received)
    audit=value['sameDeviceReplay']
    return dict(**value,phase='historical-v36',newDeviceInputs=0,
        persistenceQualifiedCompletion=None,perRunDiskMissing=27,
        limitation='27 historical process/state checks; no per-run disk capture, not cross-device acceptance')


def task3_original(reader):
    plan=task3_cases();known={};detail=[];run_ids=set()
    for batch in ['normal-v39-batch3','fault-v39-batch1']:
        root=T3+'/'+batch
        if reader.read(root+'/source-stability.json')['sourceStable'] is not True:raise ValueError('SOURCE_NOT_FROZEN')
        captured=reader.read(root+'/rows.json')
        if len({r['id'] for r in captured})!=len(captured):raise ValueError('DUPLICATE_CAPTURE_ID')
        for c in plan:
            folder=root+'/'+c['id']
            if not reader.has(folder+'/case.json'):continue
            case=reader.read(folder+'/case.json')
            expected=dict(c)
            if c['group']=='fault':expected.update(flow=SPEC.get(c['fault'],{}).get('flow'),initial=INITIALS[0])
            if canonical({k:v for k,v in case.items() if k!='caseId'})!=canonical(expected):raise ValueError('CASE_DIFFERS')
            if not reader.has(folder+'/result.json'):continue
            if c['id'] in known:raise ValueError('DUPLICATE_DEVICE_CASE')
            try:
                d={n:reader.read(folder+'/'+n+'.json') for n in ['skill','result','oracle','journal','delayed-audits','disk','before']}
                if d['result']['runId'] in run_ids:raise ValueError('DUPLICATE_RUN_ID')
                run_ids.add(d['result']['runId'])
                args=[d['skill'],case['initial'],d['result'],d['oracle'],d['journal'],d['delayed-audits'],d['disk'],case['caseId']]
                if c['group']!='fault':checked=judge_run(args);state=checked['state']
                else:
                    fault=c['fault'];ui=None;intervention=False
                    if fault in ['missing','duplicate']:
                        ui=ET.Element('hierarchy')
                        for n in reader.read(folder+'/fault-tree.json'):ET.SubElement(ui,'node',n)
                    if fault in ['cancel','foreground'] and reader.has(folder+'/intervention.json'):
                        nodes=reader.read(folder+'/intervention-overlay.json') if fault=='cancel' else []
                        intervention=intervention_proven(fault,reader.read(folder+'/intervention-before.json'),reader.read(folder+'/intervention.json'),nodes,d['result'],case['caseId'])
                    trigger=triggered(fault,d['before'],d['result'],d['oracle'],ui,intervention)
                    checked=safe_stop(fault,*args,trigger)
                    state='NOT_TRIGGERED' if not trigger else ('PASS' if checked['safeStop'] else ('FAIL' if checked['evidenceQualified'] else 'UNVERIFIED'))
                known[c['id']]=dict(id=c['id'],status=state,evidenceQualified=checked['evidenceQualified'],falseSuccess=checked['falseSuccess'],elapsedMs=checked['elapsedMs'])
                detail.append(dict(case=c,source=folder,checked=checked,inputs=len(d['result']['actions']),observations=d['result'].get('observations'),
                    skips=sum(e['kind']=='SKIP_ALREADY_AT_TARGET' for e in d['journal'])))
            except (OSError,ValueError,KeyError,TypeError,IndexError):known[c['id']]=dict(id=c['id'],status='UNVERIFIED',evidenceQualified=False)
        for row in captured:
            if row['status']!='BLOCKED' or row['id'] in known:continue
            if not row['id'].startswith('S6-') or row['reason']!='S6_SOURCE_SAVE_AMBIGUOUS_WITHOUT_STATE_CHANGE':raise ValueError('UNKNOWN_BLOCK')
            name=row['sourceFailure'].replace('\\','/')
            if not name.startswith('output/'+T3+'/'):raise ValueError('UNSAFE_BLOCK_PROOF')
            proof=reader.read(name[len('output/'):])
            if proof['end']!='REJECTED' or not proof['error']:raise ValueError('UNPROVEN_BLOCK')
            known[row['id']]=dict(id=row['id'],status='BLOCKED',evidenceQualified=False,reason=row['reason'])
    rows=[dict(c,**{k:v for k,v in known.get(c['id'],dict(status='NOT_RUN',evidenceQualified=False)).items() if k!='id'}) for c in plan]
    return dict(rows=rows,detail=detail,summary=task3_summary(rows),
        groups={g:evidence_summary([dict(r,state=r['status']) for r in rows if r['group']==g]) for g in ['single','multi','fault','challenge']},
        phase='confirmation-v39',currentCandidateV40DeviceEvidence=False,normalCompletion=sum(r['status']=='PASS' and r['group'] in ['single','multi'] for r in rows),
        safeStops=sum(r['status']=='PASS' and r['group']=='fault' for r in rows),newDeviceInputs=0)


def task4_blocked(reader):
    source=T4+'/source-export-02/failure.json';receiver=T4+'/receiver-permission-01/command-failure.json'
    proofs=[]
    for name in [source,receiver]:
        if reader.has(name):
            value=reader.read(name)
            if not value.get('reason') or value.get('paidCalls')!=0:raise ValueError('INVALID_PREPARATION_FAILURE')
            proofs.append(name)
    rows=[dict(c,status='BLOCKED' if c['group']=='chain' and proofs else 'NOT_RUN',evidenceQualified=False) for c in task4_cases()]
    return dict(rows=rows,summary=task4_summary(rows),phase='preparation-only-v40',proofs=proofs,newDeviceInputs=0,
        terminalRecords=0,settingRestored=None,scope='Installation and preparation are not business completion')


def all_historical(reader):
    return dict(task1=task1_language(reader),task2=task2_original(reader),task3=task3_original(reader),task4=task4_blocked(reader),
                newRemoteCalls=0,newDeviceInputs=0,overall='NOT_READY',noPooledOverallScore=True)
