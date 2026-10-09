"""Read-only recomputation of Task 2 evidence; not a new device trial."""
import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from flexible_device_checks import score
from task2_protocol import FLOWS, recording_match


def validate_envelope(skill,result,case,oracle,journal):
    if (result['traceId']!=skill['traceId'] or result['traceSha256']!=skill['traceSha256']
        or oracle['caseId']!=case['caseId'] or oracle['initial']!=case['initial']
        or [s['id'] for s in skill['steps']]!=FLOWS[case['flow']]):
        raise ValueError('IDENTITY_OR_FIXTURE_DIFFERS')
    if not result['startedMs']<=result['finishedMs']<=result['deadlineMs']:
        raise ValueError('EXECUTION_TIME_OUTSIDE_DECLARED_BUDGET')
    if not journal or [e['seq'] for e in journal]!=list(range(1,len(journal)+1)):
        raise ValueError('JOURNAL_SEQUENCE_INCOMPLETE')
    if any(e['runId']!=result['runId'] for e in journal):raise ValueError('JOURNAL_RUN_DIFFERS')
    if any(b['ms']<a['ms'] for a,b in zip(journal,journal[1:])):raise ValueError('JOURNAL_CLOCK_REVERSED')
    if journal[0]['kind']!='START' or journal[0]['data']!=skill:raise ValueError('JOURNAL_START_DIFFERS')
    if journal[-1]['kind']!='RESULT' or journal[-1]['data']!=result:raise ValueError('TERMINAL_RESULT_DIFFERS')
    if any(b['ms']<a['ms'] for a,b in zip(oracle['events'],oracle['events'][1:])):
        raise ValueError('ORACLE_CLOCK_REVERSED')
    indices=[a['sourceIndex'] for a in result['actions']]
    if indices!=sorted(set(indices)):raise ValueError('DISPATCH_ORDER_DIFFERS')
    for action in result['actions']:
        i=action['sourceIndex']
        if not 1<=i<=len(skill['steps']) or action['id']!=skill['steps'][i-1]['id']:
            raise ValueError('DISPATCH_ID_DIFFERS')
        if not result['startedMs']<=action['ms']<=result['finishedMs']:raise ValueError('INPUT_TIME_DIFFERS')
    return True


def guide_match(skill,guide):
    # Evaluator-owned public label specification. It cannot infer missing steps.
    expected=[]
    labels={'wfSingle':'Switch to single-page controls','wfMulti':'Switch to overview / Pages',
            'wfOpenLamp':'Open reading lamp settings','wfOpenFan':'Open fan settings'}
    for step in skill['steps']:
        key=step['id']
        if key in labels:label=labels[key]
        elif key in ('wfLampSave','wfFanSave'):
            label='Save '+('lamp' if 'Lamp' in key else 'fan')+' settings; '
            if step['afterPage'] not in ('single','overview'):return False
            label+=('stay on the single page' if step['afterPage']=='single' else 'return to overview')
        elif re.fullmatch('wfLampValue(20|40|60|80|100)',key):label='Set brightness to '+key.split('Value')[1]+'%'
        elif re.fullmatch('wfFanValue[123]',key):label='Set fan speed to '+['low','medium','high'][int(key[-1])-1]
        else:return False
        expected.append(label)
    numbered=re.findall(r'^([0-9]+)\. (.+)$',guide,re.MULTILINE)
    return ([int(i) for i,_ in numbered]==list(range(1,len(expected)+1))
            and [label for _,label in numbered]==expected)


def latency(values):
    if not values:return dict(n=0)
    ordered=sorted(values)
    return dict(n=len(values),p50Ms=ordered[math.ceil(.5*len(values))-1],
                p95Ms=ordered[math.ceil(.95*len(values))-1],maxMs=ordered[-1],method='nearest-rank')


def recompute(source):
    records={};runs=[];used_ids=set()
    for flow in FLOWS:
        base=source/(flow+'-recording')
        if not (base/'trace.json').exists():continue
        if not all((base/name).exists() for name in ('skill.json','guide.txt')):
            records[flow]=dict(outcome='NOT_RUN',reason='INCOMPLETE_RECORDING_EVIDENCE');continue
        t=json.loads((base/'trace.json').read_text(encoding='utf-8'))
        skill=json.loads((base/'skill.json').read_text(encoding='utf-8'))
        guide=(base/'guide.txt').read_text(encoding='utf-8')
        records[flow]=dict(recordingExact=recording_match(t,skill,FLOWS[flow]),
                           guideExact=guide_match(skill,guide),steps=len(skill['steps']),
                           resumed=(base/'qualification.json').exists())
    for base in sorted(source.glob('*-i*-r*')):
        if not (base/'score.json').exists():
            runs.append(dict(case=base.name,outcome='NOT_RUN',reason='INCOMPLETE_EVIDENCE'));continue
        blobs={name:(base/(name+'.json')).read_bytes() for name in ('skill','case','result','oracle','journal','score')}
        values={k:json.loads(v) for k,v in blobs.items()}
        try:
            run_id=values['result']['runId']
            if run_id in used_ids:raise ValueError('DUPLICATE_RUN_ID')
            used_ids.add(run_id)
            validate_envelope(values['skill'],values['result'],values['case'],values['oracle'],values['journal'])
            judged=score(values['skill'],values['case']['initial'],values['result'],values['oracle'],values['journal'])
            if judged!=values['score']:raise ValueError('SAVED_SCORE_DIFFERS_FROM_RECOMPUTATION')
            if not judged['correctCompletion'] or judged['falseSuccess']:raise ValueError('INDEPENDENT_CRITERIA_NOT_MET')
            runs.append(dict(case=base.name,flow=values['case']['flow'],outcome='PASS',**judged,
                             journalCorrelated=True,persistedDiskCaptured=(base/'persisted.json').exists(),
                             hashes={k:hashlib.sha256(v).hexdigest() for k,v in blobs.items()}))
        except (ValueError,KeyError,IndexError,TypeError) as error:
            runs.append(dict(case=base.name,outcome='FAIL',reason=str(error)))
    groups={flow:dict(n=sum(r.get('flow')==flow for r in runs),
                      latency=latency([r['elapsedMs'] for r in runs if r.get('flow')==flow and r['outcome']=='PASS']))
            for flow in FLOWS}
    return dict(records=records,runs=runs,scored=len(runs),passed=sum(r['outcome']=='PASS' for r in runs),
                failed=sum(r['outcome']=='FAIL' for r in runs),groups=groups,
                differentDevice=False,paidCalls=0,scope='source-emulator process/state evidence, not cross-device or per-run disk persistence')


def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Refuse overwriting prior audit')
    value=recompute(a.source);a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:value[k] for k in ('scored','passed','failed','groups','differentDevice','paidCalls')}))
    if value['failed']:raise SystemExit(1)


if __name__=='__main__':main()
