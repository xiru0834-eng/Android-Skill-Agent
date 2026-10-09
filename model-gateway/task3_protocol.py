"""Frozen two-axis workflows and independent whole-process evidence adjudication."""
import collections
from flexible_device_checks import score as process_score
from flexible_workflow import valid_goals

FLOWS={
 'S1':dict(page='single',actions=['wfLampPower','wfLampValue60','wfLampSave']),
 'S2':dict(page='single',actions=['wfFanPower','wfFanValue1','wfFanSave']),
 'S3':dict(page='single',actions=['wfLampPower','wfFanPower','wfLampValue80','wfFanValue2','wfLampSave','wfFanSave']),
 'S4':dict(page='single',actions=['wfFanPower','wfFanValue1','wfFanSave','wfLampPower','wfLampValue100','wfLampSave']),
 'S5':dict(page='single',actions=['wfLampValue20','wfLampSave','wfLampValue80','wfLampSave','wfFanPower','wfFanCancel']),
 'S6':dict(page='single',actions=['wfLampPower','wfLampPower','wfLampSave','wfFanValue1','wfFanSave']),
 'M1':dict(page='overview',actions=['wfOpenLamp','wfLampPower','wfLampValue60','wfLampSave','wfOpenFan','wfFanPower','wfFanValue1','wfFanSave']),
 'M2':dict(page='overview',actions=['wfOpenFan','wfFanPower','wfFanValue1','wfFanSave','wfOpenLamp','wfLampPower','wfLampValue60','wfLampSave']),
 'M3':dict(page='overview',actions=['wfOpenLamp','wfLampValue20','wfLampSave','wfOpenLamp','wfLampValue80','wfLampSave','wfOpenFan','wfFanValue2','wfFanSave']),
 'M4':dict(page='overview',actions=['wfOpenLamp','wfLampPower','wfLampCancel','wfOpenFan','wfFanPower','wfFanValue1','wfFanSave']),
 'M5':dict(page='overview',actions=['wfOpenLamp','wfLampPower','wfLampPower','wfLampSave','wfOpenFan','wfFanValue1','wfFanSave','wfOpenLamp','wfLampValue40','wfLampSave']),
 'M6':dict(page='overview',actions=sum((['wfOpenLamp','wfLampValue'+str(v),'wfLampSave'] for v in [20,80,40,100,60,80]),[])+['wfOpenFan','wfFanPower','wfFanValue2','wfFanSave'])}
INITIALS=[[0,40,0,3],[1,60,1,1],[0,80,1,2],[1,100,0,2]]
FAULTS=['missing','duplicate','disabled','wrong_page','input_drop','save_drop','late','stale','rollback','cancel','foreground','deadline']


def cases():
    rows=[]
    for flow in FLOWS:
        group='single' if flow[0]=='S' else 'multi'
        for i in range(3 if group=='single' else 4):
            for repeat in range(3):rows.append(dict(id=f'{flow}-i{i}-r{repeat}',group=group,flow=flow,initial=INITIALS[i],repeat=repeat))
    for fault in FAULTS:
        for repeat in range(3):rows.append(dict(id=f'F-{fault}-r{repeat}',group='fault',fault=fault,repeat=repeat))
    for fault in ['delay','navdelay']:
        for repeat in range(3):rows.append(dict(id=f'C-{fault}-r{repeat}',group='challenge',fault=fault,repeat=repeat))
    return rows


def summary(rows):
    plan={c['id']:c for c in cases()};seen={}
    for row in rows:
        key=row['id'];status=row['status']
        if key not in plan or key in seen or status not in ['PASS','FAIL','BLOCKED','NOT_RUN','UNVERIFIED','NOT_TRIGGERED']:raise ValueError('UNKNOWN_DUPLICATE_OR_INVALID_CASE')
        if status=='PASS' and row.get('evidenceQualified') is not True:raise ValueError('PASS_WITHOUT_EVIDENCE')
        seen[key]=row
    groups={}
    for group in ['single','multi','fault','challenge']:
        slots=[c for c in plan.values() if c['group']==group]
        counts=collections.Counter(seen.get(c['id'],{}).get('status','NOT_RUN') for c in slots)
        groups[group]=dict(planned=len(slots),**{k:counts[k] for k in ['PASS','FAIL','BLOCKED','NOT_RUN','UNVERIFIED','NOT_TRIGGERED']})
    return dict(protocol='T3-FLOW-1',groups=groups,verdict='PASS' if all(g['PASS']==g['planned'] for g in groups.values()) else 'NOT_READY',paidCalls=0)


def judge(skill,initial,result,oracle,journal,samples,disk,case_id):
    """No controller success flag alone, and no disk evidence borrowed from another run."""
    errors=[]
    def check(ok,reason):
        if not ok:errors.append(reason)
    try:
        check(result['traceId']==skill['traceId'] and result['traceSha256']==skill['traceSha256'],'SKILL_IDENTITY')
        check(oracle['caseId']==case_id and oracle['initial']==initial,'CASE_IDENTITY')
        check(bool(journal) and journal[0]['kind']=='START' and journal[0]['data']==skill,'START_IDENTITY')
        check(all(e['runId']==result['runId'] for e in journal),'JOURNAL_RUN_IDENTITY')
        check([e['seq'] for e in journal]==list(range(1,len(journal)+1)),'JOURNAL_SEQUENCE')
        check(all(type(e['ms']) is int for e in journal) and all(a['ms']<=b['ms'] for a,b in zip(journal,journal[1:])),'JOURNAL_CLOCK')
        check(type(result['startedMs']) is int and result['startedMs']<=result['finishedMs'] and all(result['startedMs']<=e['ms']<=result['finishedMs'] for e in journal if e['kind']!='RESULT')
              and journal[-1]['ms']>=result['finishedMs'],'RUN_CLOCK')
        terminals=[e for e in journal if e['kind']=='RESULT' and e['data'].get('status')!='RUNNING']
        running=[e for e in journal if e['kind']=='RESULT' and e['data'].get('status')=='RUNNING']
        check(len(terminals)==1 and journal[-1]['kind']=='RESULT' and journal[-1]['data']==result,'TERMINAL_RECEIPT')
        check(len(running)<=1 and all(e['stepIndex']==0 and e['phase']==0 and not e['data']['actions'] and e['data']['runId']==result['runId'] for e in running),'STARTING_RECEIPT')
        check(all(result['startedMs']<=a['ms']<min(result['finishedMs'],result['deadlineMs']) for a in result['actions']),'POST_TERMINAL_OR_DEADLINE_INPUT')
        for action in result['actions']:
            n=action['sourceIndex'];check(type(n) is int and 1<=n<=len(skill['steps']) and action['id']==skill['steps'][n-1]['id'],'ACTION_SOURCE_IDENTITY')
        confirmed=[e for e in journal if e['kind']=='STEP_CONFIRMED']
        for e in confirmed:
            n=e['data']['sourceIndex'];check(type(n) is int and 1<=n<=len(skill['steps']) and e['data']==skill['steps'][n-1],'CONFIRMED_METADATA')
            receipts=[r for r in journal if r['kind']=='CONFIRMATION_CHECK' and r['data']['sourceIndex']==n and r['seq']<e['seq']]
            check(bool(receipts),'MISSING_CONFIRMATION_RECEIPT')
            if receipts:
                receipt=receipts[-1];r=receipt['data']
                typed=all(type(r[key]) is int for key in ['observedMs','confirmationDeadlineMs','taskDeadlineMs'])
                check(typed,'CONFIRMATION_VALUE_TYPES')
                returned=[v for v in journal if v['kind']=='INPUT_RETURN' and v['stepIndex']==n-1 and v['seq']<receipt['seq']]
                skipped=[v for v in journal if v['kind']=='SKIP_ALREADY_AT_TARGET' and v['data']==skill['steps'][n-1] and v['seq']<receipt['seq']]
                window_matches=bool(returned) and r['confirmationDeadlineMs']==returned[-1]['data']['confirmationDeadlineMs']
                if skipped and not returned:
                    window_matches=r['confirmationDeadlineMs']<=min(result['deadlineMs'],skipped[-1]['ms']+result['resources']['confirmationSeconds']*1000)
                check(window_matches,'CONFIRMATION_WINDOW_IDENTITY')
                if typed:
                    check(result['startedMs']<=r['observedMs']<=receipt['ms'] and r['taskDeadlineMs']==result['deadlineMs'],'CONFIRMATION_CLOCK_IDENTITY')
                    check(r['observedMs']<min(r['confirmationDeadlineMs'],r['taskDeadlineMs']),'LATE_CONFIRMATION')
        # Ordered SETs may be skipped, but every attempted input has a concrete return receipt.
        inputs=[e for e in journal if e['kind']=='INPUT_RETURN']
        check(len(inputs)==len(result['actions']),'INPUT_RECEIPT_COUNT')
        check(all(e['data'].get('accepted') is True for e in inputs),'INPUT_NOT_ACCEPTED')
        check([e['data']['dispatchedMs'] for e in inputs]==[a['ms'] for a in result['actions']],'INPUT_RECEIPT_IDENTITY')
        final=oracle['events'][-1]
        for event in oracle['events']:
            check(valid_goals(event['saved']) and valid_goals(event['draft']),'ORACLE_VALUE_TYPES')
        check(type(samples) is list and len(samples)>=2,'DELAYED_AUDIT_MISSING')
        for sample in samples:
            last=sample['events'][-1]
            check(sample['caseId']==case_id and last['saved']==final['saved'] and last['draft']==final['draft'] and last['page']==final['page'] and last['pending']==0,'DELAYED_STATE_CHANGED')
        check(valid_goals(disk) and disk==final['saved'],'DISK_STATE_MISMATCH')
        process=process_score(skill,initial,result,oracle,journal)
        check(process['correctCompletion'],'PROCESS_OR_FINAL_MISMATCH')
        check(result['finishedMs']<result['deadlineMs'],'LATE_SUCCESS')
    except (KeyError,TypeError,IndexError,ValueError) as error:
        errors.append('MALFORMED_OR_MISSING_EVIDENCE:'+type(error).__name__);process={}
    declared=result.get('status')=='SUCCEEDED'
    # Missing/mismatched proof cannot establish a false controller success either.
    # Complete, attributable records with wrong process/state/timing can establish it.
    outcome_errors={'PROCESS_OR_FINAL_MISMATCH','DELAYED_STATE_CHANGED','DISK_STATE_MISMATCH','LATE_CONFIRMATION','LATE_SUCCESS','POST_TERMINAL_OR_DEADLINE_INPUT','INPUT_NOT_ACCEPTED'}
    qualified=not any(error not in outcome_errors for error in errors)
    return dict(correctCompletion=not errors,falseSuccess=declared and qualified and bool(errors),evidenceQualified=qualified,errors=errors,
                process=process,elapsedMs=result.get('finishedMs',0)-result.get('startedMs',0))
