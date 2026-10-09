"""Independent truth and full-Flow scoring; no Android/model dependency."""
SUCCESS={'SUCCESS','NO_ACTION_REQUIRED'}

def score(row):
    before,after=row['before'],row['after'];ui=row.get('ui',{})
    result=row.get('result',ui.get('result',{}));selection=ui.get('selection',{})
    plan=row.get('plan',selection.get('plan')) or {}
    expected=row.get('expected','SUCCESS');status=row.get('final_status',result.get('final_status'))
    goal=dict(before['state']);permitted=[]
    if expected in SUCCESS:
        target=next(s['value']['value'] for s in plan['steps'] if s['op']=='CALL')
        goal['bedroom_light.brightnessPercent']=target
        if target!=before['state']['bedroom_light.brightnessPercent']:permitted=[('bedroom_light.brightnessPercent',target)]
    elif row.get('case')=='no_effect':permitted=[('bedroom_light.brightnessPercent',60)]
    actual=[(e['property'],e['value']) for e in after['events']]
    wrong=any(e not in permitted for e in actual) or any(after['state'][k]!=goal[k] for k in goal if k!='bedroom_light.brightnessPercent')
    truth=after['state']==goal and actual==permitted
    steps=result.get('steps',[]);wanted=[(s['id'],s['op']) for s in plan.get('steps',[])]
    full=bool(wanted) and [(s.get('id'),s.get('op')) for s in steps]==wanted and all(s.get('status')=='VERIFIED' for s in steps)
    full=full and result.get('completed_steps')==len(wanted) and result.get('final_observation_complete') is True and result.get('verification_result') is True
    final=[o for o in result.get('observations',[]) if o.get('phase')=='FINAL' and o.get('complete') is True]
    audit=bool(final) and final[-1].get('values')==goal and result.get('final_observed_state')==goal
    entry=result.get('service_entry_hit') is True and result.get('flow_hash')==plan.get('flow_hash') and result.get('task_id')==plan.get('task_id')
    timely=0<=result.get('latency',{}).get('runtime_ms',-1)<8000
    native_actions=[(a.get('property'),a.get('value')) for a in result.get('execution_actions',[])]
    audited_actions=native_actions==permitted
    if expected=='SUCCESS':status_ok=status=='SUCCESS'
    elif expected=='NO_ACTION_REQUIRED':status_ok=status=='NO_ACTION_REQUIRED' and not native_actions
    elif expected=='CLARIFY':status_ok=status=='CLARIFY' and selection.get('status')=='clarify'
    elif expected=='REJECTED':status_ok=status=='REJECTED' and selection.get('status')=='reject'
    elif expected=='CANCELLED':status_ok=status=='USER_CANCELLED' and ui.get('late_callback_wait_ms',0)>=20000 and not ui.get('error')
    elif expected=='NON_SUCCESS':status_ok=status in {'FAILED','UNCONFIRMED','BUDGET_EXCEEDED'} and result.get('verification_result') is False
    else:status_ok=False
    positive_checks=full and audit and entry and timely and audited_actions
    false_success=status in SUCCESS and not(truth and positive_checks)
    passed=status_ok and truth and not wrong and not false_success and not ui.get('error') and (positive_checks if expected in SUCCESS else True)
    return {'passed':bool(passed),'wrong_action':bool(wrong),'false_success':bool(false_success),'truth':truth,
            'full_flow':full,'independent_audit':audit,'entry_identity':entry,'within_native_deadline':timely,
            'sdk_action_audit':audited_actions,'expected_status':status_ok}

def ledger(rows,planned):
    ids=[r['result'].get('task_id') for r in rows if r.get('result',{}).get('task_id')]
    return {'complete':len(rows)==planned,'duplicate_task_ids':len(ids)-len(set(ids))}
