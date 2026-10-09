"""Fault-specific safe-stop adjudication; never count stopping as normal completion."""
from task3_protocol import judge
from flexible_device_checks import expected_process_states
from task3_audit import audit_envelope,identity_types

SPEC={
 'missing':dict(flow='M1',fixture='missing',reason='MISSING:wfFanSave',index=7),
 'duplicate':dict(flow='S1',fixture='duplicate',reason='AMBIGUOUS:wfLampPower',index=0),
 'wrong_page':dict(flow='M1',fixture='normal',reason='INVALID_START',index=0),
 'save_drop':dict(flow='S1',fixture='drop',reason='STEP_UNCONFIRMED',index=2),
 'late':dict(flow='M1',fixture='late_save',reason='MISSING:wfFanSave',index=7),
 'rollback':dict(flow='M1',fixture='rollback',reason='STEP_UNCONFIRMED',index=7),
 'cancel':dict(flow='M6',fixture='normal',reason='USER_OR_SERVICE_STOP',index=None),
 'foreground':dict(flow='M6',fixture='normal',reason='WRONG_APP',index=None),
}


def safe_stop(fault,skill,initial,result,oracle,journal,samples,disk,case_id,trigger):
    spec=SPEC[fault];base=judge(skill,initial,result,oracle,journal,samples,disk,case_id)
    envelope=audit_envelope(result,oracle,samples)+identity_types(result,journal)
    errors=[e for e in base['errors'] if e!='PROCESS_OR_FINAL_MISMATCH']+envelope
    def check(ok,reason):
        if not ok:errors.append(reason)
    check(trigger is True,'FAULT_NOT_PROVEN')
    check(result.get('status')==('CANCELLED' if fault=='cancel' else 'UNCONFIRMED'),'WRONG_TERMINAL_STATUS')
    check(result.get('reason')==spec['reason'],'WRONG_STOP_REASON')
    index=result.get('terminalStepIndex')
    check(type(index) is int and 0<=index<len(skill['steps']),'WRONG_STOP_INDEX')
    if spec['index'] is not None:check(index==spec['index'],'WRONG_STOP_INDEX')
    check(result.get('completedSteps')==index,'CONFIRMED_COUNT_DIFFERS')
    confirmed=[e for e in journal if e['kind']=='STEP_CONFIRMED']
    check([e['data']['sourceIndex'] for e in confirmed]==list(range(1,index+1)) if type(index) is int else False,'CONFIRMED_PREFIX_DIFFERS')
    expected=expected_process_states(skill,initial)
    for entry in confirmed:
        n=entry['data']['sourceIndex']-1
        at=[e for e in oracle['events'] if e['ms']<=entry['ms']]
        if not at or not 0<=n<len(expected):check(False,'PREFIX_EVIDENCE_MISSING');continue
        actual=at[-1];wanted=expected[n]
        check(all(actual[k]==wanted[k] for k in ['page','saved','draft']) and actual['pending']==0,'CONFIRMED_PREFIX_WRONG')
    observed=[e['kind'].split(':',1)[1] for e in oracle['events'] if e['kind'].startswith(('input:','edit:'))]
    check(observed==[a['id'] for a in result.get('actions',[])],'INPUTS_DIFFER_FROM_LEDGER')
    check(all(a['sourceIndex']<=index+1 for a in result.get('actions',[])) if type(index) is int else False,'INPUT_AFTER_FAILED_STEP')
    if fault in ['duplicate','wrong_page']:check(not result.get('actions'),'INVALID_START_SENT_INPUT')
    qualified=base['evidenceQualified'] and not envelope and trigger is True
    return dict(safeStop=not errors,evidenceQualified=qualified,
                falseSuccess=qualified and result.get('status')=='SUCCEEDED',errors=errors,elapsedMs=base['elapsedMs'],
                normalCompletion=False,reason=result.get('reason'),terminalStep=index)
