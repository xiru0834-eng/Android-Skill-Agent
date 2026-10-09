"""Offline raw-record audit. Does not import the experiment's scorer or use ADB."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics


def check(ok, message):
    if not ok: raise ValueError(message)


def verify_row(row):
    case, before, after, report = (row[k] for k in ('case','before','after','report'))
    check([before['target'],before['other']]==case['initial'],'wrong prepared initial')
    check(before['targetClicks']==before['otherClicks']==0,'uncleared counters')
    check(before['mode']==after['mode']==case['mode'],'mode changed')
    expected=[0,0] if case['negative'] else [int(v is False) for v in case['initial']]
    actual=after['target'] is True and after['other'] is True
    observed=[after['targetClicks'],after['otherClicks']]
    if case['method']=='skill':
        issued=report['inputs']; confirmed=report['status']=='SUCCEEDED'
        false_success=confirmed and not actual
        passed=(report['desired']==[True,True] and issued==sum(expected) and observed==expected
                and (report['status']=='REFUSED' if case['negative'] else confirmed and actual))
    else:
        check(report is None,'coordinate has a fabricated self-report')
        issued=2;confirmed=false_success=None
        passed=not case['negative'] and actual and observed==expected and issued==sum(expected)
    redundant=max(sum(max(0,observed[i]-expected[i]) for i in (0,1)),issued-sum(expected))
    fields=dict(actualGoal=actual,confirmed=confirmed,falseSuccess=false_success,issuedInputs=issued,
                expectedClicks=expected,observedClicks=observed,extraInputs=redundant,
                inputsMatch=observed==expected and issued==sum(expected),**{'pass':passed})
    check(all(row[k]==v for k,v in fields.items()),'score disagrees with raw observations')


def audit(directory):
    read=lambda name:json.loads((directory/name).read_text(encoding='utf-8'))
    protocol=read('protocol.json');paths=sorted(directory.glob('[0-9][0-9][0-9]-result.json'))
    check(len(paths)==protocol['planned'],'incomplete batch')
    rows=[json.loads(p.read_text(encoding='utf-8')) for p in paths]
    run_ids=[]; groups=defaultdict(list)
    for index,row in enumerate(rows,1):
        check(paths[index-1].name==f'{index:03d}-result.json','noncontiguous trial IDs')
        check(row['case']==protocol['cases'][index-1],'schedule differs')
        verify_row(row)
        prep=read(f'{index:03d}-prepared.json')
        check(prep['before']==row['before'] and prep['case']==row['case'],'preparation changed')
        if row['report']:
            check(prep['preparation']['confirmed']==[True,True],'parameters not prepared')
            check(row['report']['package']=='edu.sydney.transferlab','wrong report package')
            check(row['report']['targets']==['edu.sydney.transferlab:id/mainToggle','edu.sydney.transferlab:id/otherToggle'],'wrong report targets')
            run_ids.append(row['report']['runId'])
        else:check(prep['points']==protocol['coordinatePoints'],'coordinates not frozen')
        c=row['case'];groups[(c['profile'],c['method'],c['name'])].append(row)
    check(len(run_ids)==len(set(run_ids)),'duplicate skill run IDs')
    root=Path(__file__).resolve().parents[1]
    for name,digest in protocol['hashes'].items():
        check(hashlib.sha256((root/name).read_bytes()).hexdigest()==digest,'source hash changed: '+name)
    check((directory/'source-skill.json').read_bytes()==Path(protocol['sourceSkill']).read_bytes(),
          'copied source skill differs')
    source=read('source-skill.json')
    historical=json.loads((root/'evaluation/gpt-skills/reuse-dev-v2/review.json').read_text(encoding='utf-8'))
    check(source==historical['skill'],'different from Samsung reviewed skill')
    check(read('integrity.json')==dict(sourceUnchanged=True,approvedSkillUnchanged=True),'final integrity failed')
    check(read('restored-display.json')==protocol['originalDisplay'],'display not restored exactly')
    result=[]
    for (profile,method,name),values in sorted(groups.items()):
        times=sorted(v['report']['elapsedMs'] for v in values if v['report'])
        result.append(dict(profile=profile,method=method,case=name,n=len(values),
            actual=sum(v['actualGoal'] for v in values),passed=sum(v['pass'] for v in values),
            extraInputs=sum(v['extraInputs'] for v in values),
            p50ms=statistics.median(times) if times else None,
            p95ms=times[math.ceil(.95*len(times))-1] if times else None))
    totals=read('summary.json');check(totals['completed']==len(rows),'summary total mismatch')
    for method in ('skill','coordinate'):
        subset=[r for r in rows if r['case']['method']==method]
        normal=[r for r in subset if not r['case']['negative']]
        abnormal=[r for r in subset if r['case']['negative']]
        times=sorted(r['report']['elapsedMs'] for r in normal) if method=='skill' else []
        calculated=dict(total=len(subset),positive=len(normal),actual=sum(r['actualGoal'] for r in normal),
            positivePass=sum(r['pass'] for r in normal),negative=len(abnormal),
            negativePass=sum(r['pass'] for r in abnormal),
            falseSuccess=sum(r['falseSuccess'] for r in subset) if method=='skill' else None,
            extraInputs=sum(r['extraInputs'] for r in subset),
            p50ms=statistics.median(times) if times else None,
            p95ms=times[math.ceil(.95*len(times))-1] if times else None)
        check(totals[method]==calculated,'summary disagrees with raw rows: '+method)
    return dict(verified=True,trials=len(rows),uniqueSkillRunIds=len(run_ids),
                sourceMatchesSamsungReview=True,displayRestored=True,groups=result)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('directory',type=Path);args=p.parse_args()
    result=audit(args.directory)
    with (args.directory/'independent-audit.json').open('x',encoding='utf-8') as stream:
        json.dump(result,stream,ensure_ascii=False,indent=2)
    print(json.dumps(result,ensure_ascii=False,indent=2))
