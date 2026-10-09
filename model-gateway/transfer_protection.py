"""Additional challenge assessment; never changes frozen primary task scores.

Missing/duplicate controls use the controller's explicit observation error plus
the frozen fixture configuration. Unlike save/drop/dirty, their presence has no
independent App event, so trigger evidence is labelled separately.
"""

ROUTE=['wfOpenLamp','wfLampPower','wfLampValue60','wfLampSave',
       'wfOpenFan','wfFanPower','wfFanValue1','wfFanSave']


def late_effects(oracle,finished_ms):
    effects=[]
    for before,after in zip(oracle['events'],oracle['events'][1:]):
        changed=[field for field in ('saved','draft','page') if before.get(field)!=after.get(field)]
        if after['ms']>finished_ms and changed:
            effects.append(dict(ms=after['ms'],kind=after['kind'],changed=changed))
    return effects


def assess(case,result,oracle,score,audit):
    fault=case['fault'];events=oracle['events'];kinds=[e['kind'] for e in events]
    reason=result['reason'];actions=[a['id'] for a in result['actions']]
    complete=(score.get('evidence_complete',False) and audit.get('actualInputsMatchRequested',False)
              and audit.get('lateAppInputs',-1)==0 and not score.get('false_success',True))
    stopped=complete and result['status']=='UNCONFIRMED'
    trigger=False;condition=False;basis='independent_app_event'
    if fault in ('delay','navdelay'):
        trigger=('save_pending' if fault=='delay' else 'navigation_pending') in kinds
        return dict(trigger_observed=trigger,trigger_basis=basis,protection_pass=None,
                    positive_challenge_pass=bool(complete and trigger and score.get('confirmed_success')))
    if fault=='dirty':
        presets=[e for e in events if e['kind']=='preset_dirty']
        trigger=bool(presets)
        if trigger:
            preset=presets[0]
            condition=(reason in ('INVALID_START','UNSAVED_USER_EDITS') and not actions
                and all(e['saved']==preset['saved'] and e['draft']==preset['draft']
                        for e in events if e['ms']>=result['startedMs']))
    elif fault=='drop':
        trigger='dropped_save' in kinds
        condition=(actions==ROUTE[:4] and reason=='STEP_UNCONFIRMED'
                   and all(e['saved']==oracle['initial'] for e in events))
    elif fault=='rollback':
        saves=[e for e in events if e['kind']=='save']
        trigger=(len(saves)>=2 and saves[0]['saved'][:2]==[1,60]
                 and saves[-1]['saved'][:2]!=[1,60] and saves[-1]['saved'][2:]==[1,1])
        condition=actions==ROUTE and reason=='FINAL_TARGET_MISMATCH'
    elif fault=='missing':
        basis='controller_error_and_frozen_fixture'
        trigger=reason=='MISSING:wfFanSave'
        condition=actions==ROUTE[:7]
    elif fault=='duplicate':
        basis='controller_error_and_frozen_fixture'
        trigger=reason=='AMBIGUOUS:wfLampPower'
        condition=actions==ROUTE[:1]
    else:
        return dict(trigger_observed=None,trigger_basis='not_a_challenge',protection_pass=None,
                    positive_challenge_pass=None)
    return dict(trigger_observed=trigger,trigger_basis=basis,
                protection_pass=bool(stopped and trigger and condition),positive_challenge_pass=None)
