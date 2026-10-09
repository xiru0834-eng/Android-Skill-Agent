"""Independent case audit. Public runtime reports do not substitute for the App oracle."""
import math
import statistics

SUCCESS={'SUCCESS','NO_ACTION_REQUIRED'}
ARMS=('P-P','E-E','P-E','E-P')


def score(row):
    goals=row['expected'];initial=row['initial_state'];observed=row.get('final_observed_state',{})
    oracle=row.get('oracle',{});actual=row.get('actual_actions',[])
    achieved=bool(goals) and all(k in oracle and oracle[k]==v for k,v in goals.items())
    observable=all(k in observed and observed[k]==v for k,v in goals.items())
    unchanged=all(k in oracle and oracle[k]==v for k,v in initial.items() if k not in goals)
    allowed=set(goals)
    wrong=any(a.get('property') not in allowed for a in actual) or not unchanged
    allowed_actions=row.get('allowed_actions')
    if allowed_actions is not None:
        sequence=[(a.get('property'),a.get('value')) for a in actual]
        wanted=[(a['property'],a['value']) for a in allowed_actions]
        wrong |= sequence!=wanted[:len(sequence)]
    evidence=row.get('evidence_complete') is True
    claimed=row['final_status'] in SUCCESS
    sequence_complete=allowed_actions is None or len(actual)==len(allowed_actions)
    false=claimed and (not achieved or not observable or not unchanged or not evidence
                      or row.get('verification_result') is not True or not sequence_complete)
    noop_ok=row['final_status']!='NO_ACTION_REQUIRED' or (
        not actual and not row.get('execution_actions') and all(initial.get(k)==v for k,v in goals.items()))
    correct=bool(row['positive'] and claimed and achieved and observable and unchanged and not wrong and not false
                 and noop_ok and evidence and row.get('frozen') is True and row.get('model_correct') is True)
    adaptation=row.get('manual_adaptation',{})
    zero=correct and all(adaptation.get(k)==0 for k in ('redemonstrations','skill_modifications','binding_modifications'))
    challenge_ok=bool(not row['positive'] and not claimed and not wrong and evidence
        and row['final_status']==row.get('expected_status',row['final_status'])
        and (row['final_status']!='REJECTED' or not actual))
    return dict(correct=correct,zero_shot=zero,false_success=false,wrong_action=wrong,
                achieved=achieved,observable=observable,challenge_correct=challenge_ok)


def wilson(success,n):
    if not n:return None
    z=1.96;p=success/n;den=1+z*z/n
    middle=(p+z*z/(2*n))/den;half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0,middle-half),min(1,middle+half)]


def summarize(rows,planned,planned_challenges=None):
    ids=[(r['arm'],r['case_id']) for r in rows]
    if len(set(ids))!=len(ids):raise ValueError('DUPLICATE_CASE_ID')
    if any(r['arm'] not in planned for r in rows):raise ValueError('UNPLANNED_ARM')
    groups={};all_pass=set(planned)==set(ARMS)
    for arm,n in planned.items():
        data=[r for r in rows if r['arm']==arm];positive=[r for r in data if r['positive']]
        if len(positive)>n:raise ValueError('EXCESS_CASES')
        judged=[score(r) for r in positive];all_judged=[score(r) for r in data]
        success=sum(v['correct'] for v in judged);zero=sum(v['zero_shot'] for v in judged)
        times=[r['latency']['total_ms'] for r in positive if 'total_ms' in r.get('latency',{})]
        groups[arm]=dict(planned=n,executed=len(positive),correct=success,rate=success/n if n else None,
            zero_shot=zero,zero_shot_rate=zero/n if n else None,wilson95=wilson(success,n),
            false_success=sum(v['false_success'] for v in all_judged),wrong_action=sum(v['wrong_action'] for v in all_judged),
            challenges=sum(not r['positive'] for r in data),challenge_correct=sum(v['challenge_correct'] for v in all_judged),
            median_total_ms=statistics.median(times) if times else None,
            p95_total_ms=sorted(times)[max(0,math.ceil(.95*len(times))-1)] if times else None)
        g=groups[arm]
        all_pass &= bool(n and len(positive)==n and success/n>=.9 and g['false_success']==g['wrong_action']==0
                         and (arm not in ('P-E','E-P') or zero==success))
        if planned_challenges is not None:
            g['planned_challenges']=planned_challenges
            all_pass &= g['challenges']==g['challenge_correct']==planned_challenges
    return dict(arms=groups,passed=bool(all_pass),scope='frozen same App and reviewed predefined bindings')
