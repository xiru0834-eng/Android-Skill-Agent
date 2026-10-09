"""Summarize completed evidence; never infer missing trials as successful."""
import json
import math
import statistics
from pathlib import Path
from named_journey_audit import audit,check_run,load
from workflow_experiment import write

def timing(values):
    values=sorted(values)
    return dict(n=len(values),p50ms=statistics.median(values),p95NearestRankMs=values[math.ceil(.95*len(values))-1],minMs=min(values),maxMs=max(values))

def main():
    root=Path('evaluation/named-journey');summary={}
    for name in ['phone-confirmation','emulator-confirmation']:
        result=audit(root/name);write(root/name/'reaudit.json',result)
        rows=load(root/name/'results.json')
        summary[name]=dict(n=result['n'],passed=result['passed'],falseSuccess=result['falseSuccess'],
            byInitial={c:dict(**timing([r['elapsed_ms'] for r in rows if r['case']['condition']==c]),
                actual=sum(r['actual_success'] for r in rows if r['case']['condition']==c),
                inputs=[r['inputs'] for r in rows if r['case']['condition']==c]) for c in ['none','partial','all']},
            uiWallClock=timing([r['ui_completion_ms'] for r in rows]))
    lang=load(root/'language-confirmation/results.json');protocol=load(root/'language-confirmation/protocol.json')['cases'];catalog=load(root/'language-confirmation/catalog.json')
    ids={k:next(s['id'] for s in catalog if s['finalGoals']==g) for k,g in [('reading',[1,60,1,1]),('bright',[1,80,1,3])]}
    assert len(lang)==len(protocol)==48
    for row,expected in zip(lang,protocol):
        assert row['case']==expected
        actual=row.get('result',{});correct=actual.get('status') in expected['acceptableStatus'] and actual.get('skill_id')==(ids[expected['expected']] if expected['expected'] else None)
        assert correct==row['correct']
    summary['language']=dict(n=48,correct=sum(r['correct'] for r in lang),**{'latency':timing([r['ms'] for r in lang])})
    summary['uiExecution']={}
    for name in ['ui-chinese','ui-english']:
        folder=root/name;data={p.stem:load(p) for p in folder.glob('*.json')};summary['uiExecution'][name]=check_run(data,data['case'])
    calls=[load(p/'response.json') for p in sorted((root/'remote-session').glob('call-*'))]
    assert len(calls)<=60
    summary['api']=dict(calls=len(calls),models=sorted({r['returned_model'] for r in calls}),inputTokens=sum(r['input_tokens'] for r in calls),outputTokens=sum(r['output_tokens'] for r in calls),cost='Not inferred from tokens; check provider billing')
    write(root/'summary.json',summary);print(json.dumps(summary,ensure_ascii=True))

if __name__=='__main__':main()
