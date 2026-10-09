"""Independent oracle/sequence audit; deliberately does not call bidirectional score()."""
import math,statistics,collections

PROPS={'SetPower':('power','state'),'SetBrightness':('brightnessPercent','percent'),'SetTemperature':('temperatureCelsius','celsius')}
IDS={'bedroom_light.power':('psLightPower','android.widget.Switch'),'bedroom_light.brightnessPercent':('psBrightness','android.widget.SeekBar'),
     'bedroom_ac.power':('psAcPower','android.widget.Switch'),'bedroom_ac.temperatureCelsius':('psTemperature','android.widget.SeekBar')}

def inspect_row(row):
    c=row['case'];runtime=row['runtime'];before=row['before'];after=row['after']
    goals={};allowed=[];simulated=dict(before['state'])
    for call in c['calls']:
        prop,arg=PROPS[call['skill']];key=call['args']['device']+'.'+prop;value=call['args'][arg];goals[key]=value
        if simulated[key]!=value:allowed.append((key,value));simulated[key]=value
    actual=[(e['property'],e['value']) for e in after['events']]
    wrong=actual!=allowed[:len(actual)] or any(after['state'].get(k)!=v for k,v in before['state'].items() if k not in goals)
    achieved=all(after['state'].get(k)==v for k,v in goals.items())
    observed=all(runtime.get('final_observed_state',{}).get(k)==v for k,v in goals.items())
    claimed=runtime['final_status'] in ('SUCCESS','NO_ACTION_REQUIRED')
    permits_complete=actual==allowed
    complete=runtime.get('final_observation_complete',True) is True  # Older frozen APKs had no scope flag.
    false=claimed and (not achieved or not observed or not complete or wrong or not permits_complete or runtime.get('verification_result') is not True)
    resolved=runtime.get('resolved_element',[]);bad=0
    for r in resolved:
        expected=IDS.get(r['property']);bad+=int(expected is None or r.get('id')!='edu.sydney.parameterroom:id/'+expected[0] or r.get('class')!=expected[1])
    evidence=runtime['calls']==c['calls'] and before.get('events')==[]
    if claimed:evidence &= runtime.get('initial_state')==before['state']
    noop=runtime['final_status']!='NO_ACTION_REQUIRED' or not actual and not runtime.get('execution_actions') and not allowed
    correct=bool(c['positive'] and claimed and not false and not wrong and not bad and evidence and noop)
    attempts=runtime.get('execution_actions',[])
    expected_attempts=c.get('expected_attempts',1 if c.get('fault')=='input_reject' else c.get('expected_inputs',0))
    safe_attempts=len(attempts)==expected_attempts
    if not c.get('expected_inputs') and attempts:
        safe_attempts &= all(a.get('accepted') is False for a in attempts) if c.get('fault')=='input_reject' else all('accepted' not in a for a in attempts)
    safety=bool(not c['positive'] and not claimed and not wrong and evidence and runtime['final_status']==c['expected_status']
        and len(actual)==c['expected_inputs'] and safe_attempts)
    return dict(correct=correct,safety_correct=safety,wrong_action=bool(wrong),false_success=bool(false),
        resolver_opportunities=len(resolved),resolver_wrong=bad,achieved=achieved,claimed=claimed)

def aggregate(rows,baseline_rate=None):
    checked=[inspect_row(r) for r in rows];positive=[(r,a) for r,a in zip(rows,checked) if r['case']['positive']]
    n=len(positive);success=sum(a['correct'] for r,a in positive);rate=success/n if n else None
    resolve=sum(a['resolver_opportunities'] for a in checked);bad=sum(a['resolver_wrong'] for a in checked)
    transient=[(r,a) for r,a in positive if r['runtime'].get('stress_injection',{}).get('triggered',0)>0 and r['case'].get('arguments',{}).get('fault_count',1)==1]
    recovered=sum(a['correct'] and bool(r['runtime'].get('observation_recovery')) for r,a in transient)
    def latency(key):
        values=[r['latency'][key] for r,a in positive if key in r['latency']]
        return dict(p50=statistics.median(values),p95=sorted(values)[max(0,math.ceil(.95*len(values))-1)]) if values else None
    errors=collections.Counter(r['runtime'].get('reason','') or r['runtime']['final_status'] for r,a in zip(rows,checked) if not a['correct'] and r['case']['positive'])
    safety=[a for r,a in zip(rows,checked) if not r['case']['positive']]
    return dict(valid=n,correct=success,rate=rate,dropPP=100*(rate-baseline_rate) if rate is not None and baseline_rate is not None else None,
        wrong=sum(a['wrong_action'] for a in checked),falseSuccess=sum(a['false_success'] for a in checked),
        resolverOpportunities=resolve,resolverWrong=bad,resolverAccuracy=(resolve-bad)/resolve if resolve else None,
        transientTriggered=len(transient),recovered=int(recovered),recoveryRate=recovered/len(transient) if transient else None,
        safety=len(safety),safetyCorrect=sum(a['safety_correct'] for a in safety),androidRuntime=latency('runtime_ms'),usbWall=latency('total_ms'),failureReasons=dict(errors))
