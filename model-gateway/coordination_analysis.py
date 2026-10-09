"""Read-only scoring of saved calls; writes derived evidence, never new API calls."""
import copy
import json
import random
import statistics
from pathlib import Path
from jev_selection_benchmark import percentile
from model_coordination import group,score
from workflow_experiment import write


def paired(rows,a,b):
    pairs={}
    for r in rows:pairs.setdefault((r['case']['caseId'],r['repeat']),{})[r['strategy']]=r
    values={}
    for (identity,_),p in pairs.items():
        if a in p and b in p:
            values.setdefault(identity,[]).append(int(p[b]['correct'])-int(p[a]['correct']))
    means=[statistics.mean(v) for v in values.values()];rng=random.Random(172940)
    draws=[statistics.mean(rng.choices(means,k=len(means))) for _ in range(2000)]
    return dict(distinctInstructionClusters=len(means),accuracyDifferenceBminusA=statistics.mean(means),
        clusterBootstrap95=[percentile(draws,.025),percentile(draws,.975)],
        caveat='All-pass degenerate intervals do not establish true equivalence; bilingual concepts are also related.')


def fallback(rows,first):
    pairs={}
    for r in rows:pairs.setdefault((r['case']['caseId'],r['repeat']),{})[r['strategy']]=r
    derived=[]
    for p in pairs.values():
        if first not in p or 'G' not in p:continue
        r,g=p[first],p['G'];use=not r['available'] or r.get('selection',{}).get('status')!='invoke'
        x=copy.deepcopy(g if use else r);x.update(strategy='counterfactual',
            ms=r['ms']+(g['ms'] if use else 0),remoteCalls=r['remoteCalls']+(g['remoteCalls'] if use else 0),
            inputTokens=(r['inputTokens'] or 0)+((g['inputTokens'] or 0) if use else 0),
            outputTokens=(r['outputTokens'] or 0)+((g['outputTokens'] or 0) if use else 0),fallback=use)
        derived.append(score(x))
    return dict(offlineCounterfactual=True,latencyIsSumOfIndependentCallsNotLiveMeasurement=True,
        addedGptCalls=sum(r['fallback'] for r in derived),stats=group(derived))


def main():
    root=Path(__file__).resolve().parents[1]/'evaluation/model-coordination-v1'
    first=json.loads((root/'confirmation/results.json').read_text(encoding='utf-8'))
    second=json.loads((root/'literal-miss/results.json').read_text(encoding='utf-8'))
    result=dict(actualSelectionDecisions=len(first)+len(second),
        actualRemoteCalls=sum(r['remoteCalls'] for r in first+second),
        firstStagePairs={k:paired(first,'G',k) for k in ['J','C','R']},
        literalMissPairs={k:paired(second,'G',k) for k in ['F','R']},
        naiveFallback={k:fallback(second,k) for k in ['F','R']},
        failures=[dict(stage=stage,case=r['case']['caseId'],repeat=r['repeat'],strategy=r['strategy'],
            status=r.get('selection',{}).get('status'),modelChoice=r.get('modelAnswer',{}).get('choice'),
            confidence=r.get('modelAnswer',{}).get('confidence'),error=r.get('error'))
            for stage,rows in [('main',first),('literal-miss',second)] for r in rows if not r['correct']])
    phone=root/'phone/results.json'
    if phone.exists():
        from jev_deployment_smoke import verify_execution
        rows=json.loads(phone.read_text(encoding='utf-8'))
        for r in rows:verify_execution(r,partial=True)
        stats={}
        for backend in ['gpt','routed-full']:
            data=[r for r in rows if r['backend']==backend]
            stats[backend]=dict(n=len(data),actualAndConfirmed=sum(r['actual_success'] and r['confirmed_success'] for r in data),
                falseSuccess=sum(r['false_success'] for r in data),nonTargetViolations=sum(r['non_target_violation'] for r in data),
                extraInputs=sum(r['extraInputs'] for r in data),unexpectedInputs=sum(r['unexpectedInputs'] for r in data),
                afterDeadlineInputs=sum(r['afterDeadlineInputs'] for r in data),postTerminalInputs=sum(r['post_terminal_inputs'] for r in data),
                selectionP50ms=statistics.median(r['selectionMs'] for r in data),executionP50ms=statistics.median(r['elapsed_ms'] for r in data),
                coreStageSumP50ms=statistics.median(r['coreStageSumMs'] for r in data),remoteCalls=sum(r['remoteCalls'] for r in data))
        result['phone']=stats
    write(root/'analysis.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['failures','firstStagePairs','literalMissPairs']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
