"""Independent private-state adjudicator. Never imported by the UI controller."""

DOMAINS=({0,1},{20,40,60,80,100},{0,1},{1,2,3})

def valid_values(values,optional=False):
    return (isinstance(values,list) and len(values)==4 and all(
        (optional and value is None) or (type(value) is int and value in DOMAINS[i])
        for i,value in enumerate(values)))

def score(oracle, result, goal):
    initial = oracle.get('initial')
    events = oracle.get('events', [])
    if oracle.get('schema') != 1 or not valid_values(initial) or not events:
        raise ValueError('Missing initial evidence')
    if not valid_values(goal,optional=True) or not any(x is not None for x in goal):
        raise ValueError('Missing task goal')
    end, start = result['finishedMs'], result['startedMs']
    if end<start or events[0]['ms']>start or events[0]['kind']!='initial' or events[0]['saved']!=initial:
        raise ValueError('Invalid run boundaries')
    previous=-1
    for event in events:
        if event['ms']<previous or not valid_values(event['saved']) or not valid_values(event['draft']):
            raise ValueError('Invalid ledger')
        previous=event['ms']
    eligible=[e for e in events if e['ms']<=end]
    if not eligible: raise ValueError('No state at terminal time')
    terminal=eligible[-1]
    requested=[i for i,v in enumerate(goal) if v is not None]
    protected=[i for i,v in enumerate(goal) if v is None]
    def good(e):
        return (all(e['saved'][i]==goal[i] for i in requested)
                and all(e['saved'][i]==initial[i] for i in protected)
                and e['saved']==e['draft'] and e['page'] in ('single','overview')
                and e['pending']==0)
    # Include transient edits and post-terminal audit events; never reward a late commit.
    observed=[e for e in events if e['ms']>=start]
    violation=any(any(e['saved'][i]!=initial[i] or e['draft'][i]!=initial[i] for i in protected) for e in observed)
    stable=all(good(e) for e in events if e['ms']>end)
    late_inputs=[a for a in result.get('actions',[]) if a['ms']>end]
    actual=good(terminal) and stable and not violation and not late_inputs and end<=result['deadlineMs']
    claimed=result['status']=='SUCCEEDED'
    return dict(actual_success=actual,confirmed_success=actual and claimed,
                false_success=claimed and not actual,unconfirmed_success=actual and not claimed,
                non_target_violation=violation,post_terminal_inputs=len(late_inputs),
                goal_fields_met=sum(terminal['saved'][i]==goal[i] for i in requested),
                goal_fields=len(requested),terminal_saved=terminal['saved'],
                elapsed_ms=end-start,status=result['status'],inputs=len(result.get('actions',[])))
