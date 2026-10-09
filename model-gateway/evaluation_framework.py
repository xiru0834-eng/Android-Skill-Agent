"""Versioned offline evaluation. Unknown evidence is never a successful trial."""
import math
import statistics
from collections import Counter, defaultdict

VERSION='framework-1'
REQUIRED={
    'teaching':('record_complete','faithful','saved'),
    'language':('decision_correct',),
    'execution':('audit_complete','task_confirmed','protected','input_safe','route'),
    'migration':('same_skill','local_review'),
    'fault':('audit_complete','expected_stop','protected','input_safe'),
    'ux':('no_execution','no_inputs'),
}
STATES=('PASS','FAIL','BLOCKED','INVALID','NOT_RUN')
PAIR_FIELDS=('dataset','app','device','display','budget_ms','auditor','changed_factor')
COUNTERS=('input_violations','post_terminal_inputs','extra_inputs','input_count')
BOOLEANS=('actual_success','reported_success','non_target_violation')
TIMINGS=('execution_ms','model_ms','e2e_ms','teaching_ms','transfer_ms')


def ratio(k,n):
    if type(k) is not int or type(n) is not int or not 0<=k<=n:
        raise ValueError('Invalid binomial counts')
    if not n:return dict(numerator=k,denominator=n,value=None,wilson95=None)
    p=k/n;z=1.959963984540054;d=1+z*z/n
    center=(p+z*z/(2*n))/d
    radius=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    low=0 if k==0 else max(0,center-radius)
    high=1 if k==n else min(1,center+radius)
    return dict(numerator=k,denominator=n,value=p,wilson95=[low,high])


def validate_plan(p):
    if p.get('schema')!=1 or p.get('framework')!=VERSION:
        raise ValueError('Unknown evaluation version')
    for key in ('campaign','variant','phase'):
        if not isinstance(p.get(key),str) or not p[key]:raise ValueError('Missing '+key)
    if p['phase'] not in ('development','confirmation','retrospective'):
        raise ValueError('Unknown experimental phase')
    caps=p.get('capabilities');cases=p.get('cases')
    if not isinstance(caps,list) or not isinstance(cases,list):raise ValueError('Missing lists')
    ids=[c.get('id') for c in caps]
    if any(not isinstance(i,str) or not i for i in ids) or len(set(ids))!=len(ids):
        raise ValueError('Invalid capability IDs')
    seen=set();repeats=set()
    for c in cases:
        if not isinstance(c.get('id'),str) or not c['id'] or c['id'] in seen:
            raise ValueError('Duplicate or empty case ID')
        seen.add(c['id'])
        if c.get('stage') not in REQUIRED:raise ValueError('Unknown stage')
        if type(c.get('repeat')) is not int or c['repeat']<0:raise ValueError('Bad repeat')
        if any(not isinstance(c.get(k),str) or not c[k] for k in ('family','environment','expected')):
            raise ValueError('Missing case grouping')
        group=(c['stage'],c['environment'],c['family'],c['repeat'])
        if group in repeats:raise ValueError('Duplicate trial repetition')
        repeats.add(group)
        if not isinstance(c.get('dimensions'),dict):raise ValueError('Missing dimensions')
        tags=c.get('capabilities')
        if not isinstance(tags,list) or not tags or len(set(tags))!=len(tags) or not set(tags)<=set(ids):
            raise ValueError('Unknown or duplicate capability')
    return p


def check_metrics(m):
    if not isinstance(m,dict):raise ValueError('Invalid metrics')
    for key in COUNTERS:
        v=m.get(key)
        if v is not None and (type(v) is not int or v<0):raise ValueError('Bad '+key)
    for key in BOOLEANS:
        if m.get(key) is not None and type(m[key]) is not bool:raise ValueError('Bad '+key)
    timings=m.get('timings',{})
    if not isinstance(timings,dict) or not set(timings)<=set(TIMINGS):raise ValueError('Bad timing scope')
    for value in timings.values():
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value<0):
            raise ValueError('Bad timing value')


def classify(c,o):
    row=dict(c,metrics={},checks={},evidence_basis=None,error=None)
    if o is None:return dict(row,state='NOT_RUN')
    m=o.get('metrics',{});check_metrics(m)
    row.update(metrics=m,checks=o.get('checks',{}),evidence_basis=o.get('evidence_basis'),
               error=o.get('error'),evidence=o.get('evidence'))
    if o.get('state') in ('BLOCKED','INVALID'):return dict(row,state=o['state'])
    if o.get('state')!='SCORED':raise ValueError('Unknown observation state')
    checks=row['checks']
    if not isinstance(checks,dict) or any(type(checks.get(k)) is not bool for k in REQUIRED[c['stage']]):
        return dict(row,state='INVALID',error='Missing or non-boolean required check')
    if 'audit_complete' in checks and not checks['audit_complete']:
        return dict(row,state='INVALID',error='Audit incomplete')
    # Guard contradictory normalized records before they can inflate a score.
    derived={}
    if m.get('actual_success') is not None and m.get('reported_success') is not None:
        derived['task_confirmed']=m['actual_success'] and m['reported_success']
    if m.get('non_target_violation') is not None:derived['protected']=not m['non_target_violation']
    if all(m.get(k) is not None for k in ('input_violations','post_terminal_inputs','extra_inputs')):
        derived['input_safe']=not (m['input_violations'] or m['post_terminal_inputs'] or m['extra_inputs'])
    if any(k in checks and checks[k]!=v for k,v in derived.items()):
        return dict(row,state='INVALID',error='Checks contradict measured outcome')
    failed=[k for k in REQUIRED[c['stage']] if not checks[k]]
    if 'exec.zero' in c['capabilities']:
        if m.get('input_count') is None:return dict(row,state='INVALID',error='Zero-input count unmeasured')
        if m['input_count']!=0:failed.append('zero_input')
    if 'teach.automated' in c['capabilities'] and c['dimensions'].get('source')!='AUTOMATED':
        return dict(row,state='INVALID',error='Demonstration provenance unknown')
    return dict(row,state='FAIL' if failed else 'PASS',failed_checks=failed)


def timing_stats(values,planned):
    values=sorted(values)
    return dict(n=len(values),missing=planned-len(values),
                p50=statistics.median(values) if values else None,
                p95=values[math.ceil(.95*len(values))-1] if values else None,
                max=max(values) if values else None)


def group_stats(rows):
    count=Counter(r['state'] for r in rows);scored=[r for r in rows if r['state'] in ('PASS','FAIL')]
    pairs=[r['metrics'] for r in scored if all(type(r['metrics'].get(k)) is bool
                                               for k in ('actual_success','reported_success'))]
    false=sum(m['reported_success'] and not m['actual_success'] for m in pairs)
    claim=sum(m['reported_success'] for m in pairs)
    protected=[r['metrics']['non_target_violation'] for r in scored
               if type(r['metrics'].get('non_target_violation')) is bool]
    stats=dict(planned=len(rows),scored=len(scored),states={s:count[s] for s in STATES},
               pass_planned=ratio(count['PASS'],len(rows)),pass_scored=ratio(count['PASS'],len(scored)),
               actual_completion=ratio(sum(m['actual_success'] for m in pairs),len(pairs)),
               confirmed_completion=ratio(sum(m['actual_success'] and m['reported_success'] for m in pairs),len(pairs)),
               false_success=ratio(false,len(pairs)),false_among_claims=ratio(false,claim),
               unconfirmed_actual=sum(m['actual_success'] and not m['reported_success'] for m in pairs),
               non_target_violation=ratio(sum(protected),len(protected)),
               timings={k:timing_stats([r['metrics']['timings'][k] for r in rows if r['state']!='INVALID'
                           if r['metrics'].get('timings',{}).get(k) is not None],len(rows)) for k in TIMINGS})
    decisions=[r['metrics'] for r in scored if type(r['metrics'].get('positive')) is bool]
    if decisions:
        stats['language_groups']={}
        for positive in (True,False):
            selected=[r for r in scored if r['metrics'].get('positive') is positive]
            stats['language_groups']['positive' if positive else 'negative']=dict(
                correct=ratio(sum(r['state']=='PASS' for r in selected),len(selected)),
                false_invokes=sum(r['metrics'].get('false_invoke',False) for r in selected))
    stats['inputs']={k:dict(total=sum(r['metrics'][k] for r in scored if r['metrics'].get(k) is not None),
                          measured=sum(r['metrics'].get(k) is not None for r in scored),
                          missing=len(rows)-sum(r['metrics'].get(k) is not None for r in scored)) for k in COUNTERS}
    return stats


def summarize(p,observations):
    validate_plan(p);seen={};allowed={c['id'] for c in p['cases']}
    for o in observations:
        key=o.get('case_id')
        if key not in allowed or key in seen:raise ValueError('Duplicate or unplanned observation')
        seen[key]=o
    rows=[classify(c,seen.get(c['id'])) for c in p['cases']]
    stages={stage:group_stats([r for r in rows if r['stage']==stage]) for stage in REQUIRED
            if any(r['stage']==stage for r in rows)}
    for stage,stats in stages.items():
        stats['environments']={env:group_stats([r for r in rows if r['stage']==stage and r['environment']==env])
                              for env in sorted({r['environment'] for r in rows if r['stage']==stage})}
    caps={}
    for cap in p['capabilities']:
        relevant=[r for r in rows if cap['id'] in r['capabilities']];scored=[r for r in relevant if r['state'] in ('PASS','FAIL')]
        families=defaultdict(list)
        for r in scored:families[(r['environment'],r['family'])].append(r)
        minimum=min((len(v) for v in families.values()),default=0)
        inconsistent=sum(len({r['state'] for r in v})>1 for v in families.values())
        states=Counter(r['state'] for r in relevant)
        status=('NOT_TESTED' if not relevant else 'INSUFFICIENT_EVIDENCE' if not scored or len(scored)<len(relevant)
                else 'OBSERVED_FAILURE' if states['FAIL'] else 'OBSERVED_PASS')
        caps[cap['id']]=dict(cap,**group_stats(relevant),status=status,unique_families=len(families),
                            minimum_repeats=minimum,inconsistent_families=inconsistent,
                            evidence_level='REPEATED' if minimum>=3 and inconsistent==0 else 'SMALL_SAMPLE')
    alerts=[]
    if any(s['false_success']['numerator'] for s in stages.values()):alerts.append('false_success')
    if any(s['non_target_violation']['numerator'] for s in stages.values()):alerts.append('non_target_violation')
    if any(s['inputs'][k]['total'] for s in stages.values() for k in ('input_violations','post_terminal_inputs','extra_inputs')):
        alerts.append('input_violation_or_extra_input')
    if any(r['state'] in ('BLOCKED','INVALID','NOT_RUN') for r in rows):alerts.append('incomplete_evaluation')
    return dict(schema=1,framework=VERSION,campaign=p['campaign'],variant=p['variant'],phase=p['phase'],
                comparison=p.get('comparison',{}),stages=stages,capabilities=caps,cases=rows,alerts=alerts,
                limitations=['Fixed-task repeats may be dependent; Wilson intervals are descriptive.',
                             'No pooled overall score; language, safe stops and task completion differ.'])


def compare_reports(a,b):
    for report in (a,b):
        cases=report.get('cases')
        if report.get('schema')!=1 or report.get('framework')!=VERSION or not isinstance(cases,list):
            return dict(status='INCOMPARABLE',reasons=['report_contract'])
        if any(not isinstance(r,dict) or 'id' not in r for r in cases) or len({r['id'] for r in cases})!=len(cases):
            return dict(status='INCOMPARABLE',reasons=['duplicate_or_invalid_cases'])
    reasons=[]
    if a.get('framework')!=b.get('framework'):reasons.append('scoring_version')
    for k in PAIR_FIELDS:
        av,bv=a.get('comparison',{}).get(k),b.get('comparison',{}).get(k)
        if av is None or bv is None or av!=bv:reasons.append(k)
    fields=('id','stage','family','repeat','environment','expected','dimensions','capabilities')
    am={r['id']:r for r in a['cases']};bm={r['id']:r for r in b['cases']}
    if set(am)!=set(bm):reasons.append('case_set')
    elif any(any(am[i][k]!=bm[i][k] for k in fields) for i in am):reasons.append('case_conditions')
    if reasons:return dict(status='INCOMPARABLE',reasons=reasons)
    pairs=[(am[i],bm[i]) for i in sorted(am) if am[i]['state'] in ('PASS','FAIL') and bm[i]['state'] in ('PASS','FAIL')]
    ap=sum(x['state']=='PASS' for x,y in pairs);bp=sum(y['state']=='PASS' for x,y in pairs)
    deltas=[y['metrics']['timings']['execution_ms']-x['metrics']['timings']['execution_ms'] for x,y in pairs
            if all(r['metrics'].get('timings',{}).get('execution_ms') is not None for r in (x,y))]
    return dict(status='DESCRIPTIVE_PAIRED',n=len(pairs),unpaired_or_unknown=len(am)-len(pairs),
                both_pass=sum(x['state']==y['state']=='PASS' for x,y in pairs),
                a_only=sum(x['state']=='PASS' and y['state']=='FAIL' for x,y in pairs),
                b_only=sum(y['state']=='PASS' and x['state']=='FAIL' for x,y in pairs),
                both_fail=sum(x['state']==y['state']=='FAIL' for x,y in pairs),
                observed_pass_delta=(bp-ap)/len(pairs) if pairs else None,
                by_stage={stage:dict(n=sum(x['stage']==stage for x,y in pairs),
                    a_only=sum(x['stage']==stage and x['state']=='PASS' and y['state']=='FAIL' for x,y in pairs),
                    b_only=sum(x['stage']==stage and y['state']=='PASS' and x['state']=='FAIL' for x,y in pairs))
                    for stage in {x['stage'] for x,y in pairs}},
                pairs=[dict(case_id=x['id'],stage=x['stage'],a=x['state'],b=y['state'],
                            a_error=x.get('error'),b_error=y.get('error')) for x,y in pairs],
                execution_delta_ms=timing_stats(deltas,len(pairs)) if not deltas else
                    dict(n=len(deltas),missing=len(pairs)-len(deltas),median=statistics.median(deltas)),
                conclusion='Observed paired difference only; no automatic causal or significance claim.')
