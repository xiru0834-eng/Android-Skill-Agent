"""Summarize complete confirmation batches; keep pilot/operator failures separate."""
import json,statistics
from pathlib import Path
from partial_audit import audit,load,check_run
from named_journey_audit import check_run as check_legacy
from workflow_experiment import write

ROOT=Path('evaluation/partial-workflow')
def main():
    out={}
    for name in ['phone-matrix','emulator-reference','emulator-compact-final']:
        result=audit(ROOT/name);write(ROOT/name/'reaudit.json',result);rows=result['checks']
        out[name]={k:v for k,v in result.items() if k!='checks'}
        for mode,filtered in [('needsInput',[r for r in rows if r['case']['condition']!='all']),('already',[r for r in rows if r['case']['condition']=='all'])]:
            ms=[r['elapsed_ms'] for r in filtered];out[name][mode]=dict(n=len(ms),medianMs=statistics.median(ms),minMs=min(ms),maxMs=max(ms),inputs=sum(r['inputs'] for r in filtered))
        out[name]['unexpectedInputs']=sum(r['unexpectedInputs'] for r in rows);out[name]['extraInputs']=sum(r['extraInputs'] for r in rows)
    lang=load(ROOT/'language/results.json');out['language']=dict(n=len(lang),correct=sum(r['correct'] for r in lang),positive=sum(r['correct'] and r['case']['expected'] is not None for r in lang),negative=sum(r['correct'] and r['case']['expected'] is None for r in lang),medianMs=statistics.median(r['ms'] for r in lang))
    for name in ['ui-chinese','ui-english']:
        d={p.stem:load(p) for p in (ROOT/name).glob('*.json')};out[name]=check_run(d,d['case'])
    for name in ['legacy-reading-final','legacy-original']:
        d={p.stem:load(p) for p in (ROOT/name).glob('*.json')};out[name]=check_legacy(d,d['case'])
    faults=load(ROOT/'faults/results.json');out['faults']=dict(n=len(faults),correctStop=sum(r['passFailureCriteria'] for r in faults),falseSuccess=sum(r['false_success'] for r in faults))
    out['uiSafety']={name:load(ROOT/name/'evidence.json')['passCriteria'] for name in ['ui-reject','ui-confirm-cancel']}
    out['setupIssues']=['Samsung accessibility service required normal Settings reconnection after installation','Emulator System UI ANR before task execution; screenshot preserved','Two old-skill regression attempts failed before execution due to operator scrolling overshoot; bounded short bidirectional swipes fixed; failed folders retained']
    out['remoteCalls']=len(list((ROOT/'remote').glob('call-*')))
    remote=[load(p) for p in (ROOT/'remote').glob('call-*/response.json')]
    out['remoteUsage']=dict(models=sorted({r['returned_model'] for r in remote}),inputTokens=sum(r['input_tokens'] for r in remote),outputTokens=sum(r['output_tokens'] for r in remote))
    out['setupIssues'].append('Compact first attempt failed caseId/initial acknowledgement before executor start. Delayed reset is a working hypothesis, not a proven cause: the mismatching value was not retained. Bounded read-only acknowledgement polling added; identical protocol rerun in a separate folder.')
    out['setupIssues'].append('Compact second attempt reached library button after the final allowed scroll but did not reread it. Operator now permits up to 32 short scrolls and checks after the last one; executor has no scrolling change.')
    write(ROOT/'summary.json',out);print(json.dumps(out,ensure_ascii=True,indent=2))

if __name__=='__main__':main()
