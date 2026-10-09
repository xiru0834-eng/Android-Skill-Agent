"""Frozen Task 2 denominators and read-only evidence checks. No device/model calls."""
import argparse
import hashlib
import json
from pathlib import Path
from workflow_contract import compile_evidence

FLOWS={
    'P':['wfOpenLamp','wfLampValue80','wfLampSave'],
    'R':['wfOpenFan','wfFanValue2','wfFanSave','wfOpenLamp','wfLampValue100','wfLampSave'],
    'V':['wfSingle','wfLampValue20','wfLampSave','wfLampValue80','wfLampSave','wfMulti'],
}
INITIALS=[[0,40,0,3],[1,60,1,1],[0,80,1,2]]
NEGATIVES=['empty','all_cancelled','overlap','missing_observation','ambiguous_attribution',
           'invalid_save','unfinished_page','repeated_stop','cancel_review','duplicate_name',
           'tampered_package','process_reentry']


def plan():
    rows=[]
    for flow,actions in FLOWS.items():
        for language in ('zh','en'):
            rows.append(dict(id=f'C-{flow}-{language}',group='teaching',flow=flow,language=language,
                             initial=INITIALS[0],actions=actions,source='AUTOMATED'))
        for index,initial in enumerate(INITIALS):
            for repeat in range(3):
                rows.append(dict(id=f'D-{flow}-i{index}-r{repeat}',group='reuse',flow=flow,
                                 sourceCase=f'C-{flow}-en',initial=initial,repeat=repeat,
                                 requiresDifferentDevice=True))
    for category in NEGATIVES:
        for repeat in range(2):
            rows.append(dict(id=f'E-{category}-{repeat}',group='negative',category=category,repeat=repeat))
    return dict(protocol='T2-TEACH-1',paidCalls=0,cases=rows)


def recording_match(trace,skill,expected_actions):
    try:
        valid=compile_evidence(trace)
        ids=[s['id'] for s in trace['steps']]
        indices=[s['sourceIndex'] for s in skill['steps']]
        return (trace['source']=='AUTOMATED' and valid==skill and ids==expected_actions
                and [s['id'] for s in skill['steps']]==ids and indices==list(range(1,len(ids)+1)))
    except (ValueError,KeyError,TypeError):return False


def file_match(source,target):
    if not source or not target:return False
    return hashlib.sha256(source).hexdigest()==hashlib.sha256(target).hexdigest()


def summarize(frozen,observations):
    expected={r['id']:r for r in frozen['cases']}
    if len(expected)!=len(frozen['cases']):raise ValueError('DUPLICATE_PLANNED_ID')
    seen={}
    for row in observations:
        if row.get('id') not in expected or row['id'] in seen:raise ValueError('UNKNOWN_OR_DUPLICATE_RESULT')
        if row.get('outcome') not in ('PASS','FAIL','BLOCKED','NOT_RUN','NOT_TRIGGERED'):raise ValueError('INVALID_OUTCOME')
        if row['outcome']=='PASS':
            facts=row.get('facts',{})
            kind=expected[row['id']]['group']
            if kind=='teaching':
                keys=['recordingExact','guideExact','savedPersistent','normalFilePath','hashExact','approvalIsolated']
            elif kind=='reuse':
                keys=['samePackage','differentDevice','reviewedOnTarget','correctCompletion','orderedProcess','untouched','persisted']
            else:keys=['triggered','expectedHandling','oldStateProtected','noExecution']
            if any(facts.get(k) is not True for k in keys):raise ValueError('PASS_WITHOUT_REQUIRED_FACTS')
        seen[row['id']]=row
    groups={}
    for group in ('teaching','reuse','negative'):
        ids=[key for key,row in expected.items() if row['group']==group]
        counts={state:sum(seen.get(key,{}).get('outcome','NOT_RUN')==state for key in ids)
                for state in ('PASS','FAIL','BLOCKED','NOT_RUN','NOT_TRIGGERED')}
        groups[group]=dict(planned=len(ids),**counts)
    return dict(protocol=frozen['protocol'],groups=groups,
                verdict='AUTOMATED_VALIDATION_PASS' if all(g['PASS']==g['planned'] for g in groups.values()) else 'NOT_READY',
                paidCalls=0,humanUsability='NOT_TESTED')


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ledger',type=Path);a=p.parse_args()
    if a.output.exists():p.error('Refuse overwriting evidence')
    if a.ledger:
        value=summarize(plan(),json.loads(a.ledger.read_text(encoding='utf-8')))
    else:value=plan()
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    print(value.get('verdict',f"Frozen {len(value['cases'])} cases") if 'cases' in value else value['verdict'])


if __name__=='__main__':main()
