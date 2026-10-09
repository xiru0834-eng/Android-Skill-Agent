"""Task5 additive contracts; reuse framework-1, never a pooled quality score."""
import json
import math
import random
import re
from pathlib import PurePosixPath
from evaluation_framework import ratio
from task3_protocol import INITIALS

MAX_BYTES=8388608


def safe_name(name):
    if (not isinstance(name,str) or not name or '\\' in name or ':' in name
            or name.startswith('/') or any(p in ('','.','..') for p in name.split('/'))):
        raise ValueError('UNSAFE_RELATIVE_PATH')
    return PurePosixPath(name)


def decode(blob):
    if type(blob) is not bytes or not 0<len(blob)<=MAX_BYTES:raise ValueError('FILE_SIZE')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('DUPLICATE_KEY')
            if key.lower() in {'authorization','api_key','apikey','pairing','password','secret'}:raise ValueError('SENSITIVE_FIELD')
            result[key]=value
        return result
    def constant(_):raise ValueError('NON_FINITE')
    try:
        text=blob.decode('utf-8','strict')
        if re.search(r'(?:sk-proj-|apikey_)[A-Za-z0-9_-]{16,}',text):raise ValueError('SENSITIVE_VALUE')
        return json.loads(text,object_pairs_hook=pairs,parse_constant=constant)
    except (UnicodeError,json.JSONDecodeError) as error:raise ValueError('INVALID_JSON_OR_UTF8') from error


def latency(values,planned):
    if type(planned) is not int or planned<0 or len(values)>planned:raise ValueError('LATENCY_DENOMINATOR')
    if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values):raise ValueError('LATENCY_VALUE')
    ordered=sorted(values);n=len(ordered)
    return dict(n=n,missing=planned-n,p50Ms=ordered[math.ceil(.5*n)-1] if n else None,
                p95Ms=ordered[math.ceil(.95*n)-1] if n else None,maxMs=ordered[-1] if n else None,method='nearest-rank')


def stable_repeats(rows,expected=3):
    if type(expected) is not int or expected<1:raise ValueError('REPEAT_COUNT')
    groups={}
    for family,repeat,correct in rows:
        if type(repeat) is not int or not 0<=repeat<expected or type(correct) is not bool:raise ValueError('REPEAT_VALUE')
        seen=groups.setdefault(family,{})
        if repeat in seen:raise ValueError('DUPLICATE_REPEAT')
        seen[repeat]=correct
    full=sum(len(g)==expected for g in groups.values())
    good=sum(len(g)==expected and all(g.values()) for g in groups.values())
    return dict(families=len(groups),complete=full,allCorrect=good,incomplete=len(groups)-full,
                atLeastOneFailure=sum(not all(g.values()) for g in groups.values()),rate=ratio(good,len(groups)),
                independentUsers=False)


def paired_plan(skill_hashes):
    if set(skill_hashes)!={'S3','M1','M4'} or any(not re.fullmatch('[a-f0-9]{64}',v) for v in skill_hashes.values()):raise ValueError('SKILL_HASHES')
    rows=[];rng=random.Random(500731)
    for display in ['D0','D2']:
        for appearance in ['native','reordered']:
            order=[['A','B']]*4+[['B','A']]*5 if len(rows)%18==0 else [['A','B']]*5+[['B','A']]*4
            rng.shuffle(order)
            for flow in ['S3','M1','M4']:
                for i in range(3):
                    rows.append(dict(id=f'{display}-{appearance}-{flow}-i{i}',flow=flow,initial=INITIALS[i][:],
                        display=display,appearance=appearance,order=order.pop(),budgetMs=60000,inputLimit=24,
                        package='edu.sydney.transferlab',skillSha256=skill_hashes[flow]))
    return dict(schema=1,protocol='T5-PAIRED-1',phase='exploratory',seed=500731,cases=rows,
                attemptsPlanned=72,baselineCoordinates='NOT_CAPTURED',deviceExecution='NOT_RUN',
                modelCallsAllowed=0,claim='Same-app display/layout exploration, not arbitrary-app or physical-device proof')


def paired_stats(plan,rows):
    slots={c['id']:c for c in plan['cases']};seen={}
    if plan.get('protocol')!='T5-PAIRED-1' or len(slots)!=36 or len(plan['cases'])!=36:raise ValueError('PAIR_PROTOCOL')
    for row in rows:
        key=(row['id'],row['arm'])
        if (key in seen or row['id'] not in slots or row['arm'] not in ['A','B']
                or json.dumps(row['conditions'],sort_keys=True)!=json.dumps(slots[row['id']],sort_keys=True)
                or any(type(row[k]) is not bool for k in ['success','safetyChecked','safetyViolation'])):raise ValueError('PAIR_IDENTITY_OR_CONDITIONS')
        seen[key]=row
    pairs=[(seen[(i,'A')],seen[(i,'B')]) for i in slots if (i,'A') in seen and (i,'B') in seen]
    n=len(pairs);a=sum(x['success'] and not y['success'] for x,y in pairs);b=sum(y['success'] and not x['success'] for x,y in pairs);d=a+b
    p=min(1.0,2*sum(math.comb(d,k) for k in range(min(a,b)+1))/2**d) if d else 1.0
    violation=any(r['safetyViolation'] for r in rows)
    checked=len(rows)==72 and all(r['safetyChecked'] for r in rows)
    return dict(n=n,missingPairs=36-n,aOnly=a,bOnly=b,bothPass=sum(x['success'] and y['success'] for x,y in pairs),
        bothFail=sum(not x['success'] and not y['success'] for x,y in pairs),delta=(b-a)/n if n else None,
        exactTwoSidedP=p if n else None,safetyGate='FAIL' if violation else ('PASS' if checked else 'UNVERIFIED'),
        conclusion='EXPLORATORY_ONLY' if n else 'NOT_RUN')
