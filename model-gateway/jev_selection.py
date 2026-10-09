"""Opt-in TypeSafe Choice adapter. It proposes a reviewed ID, never phone input.

API shape: https://docs.typesafe.ai/api
Version / text-only input: https://docs.typesafe.ai/models
"""
import json
import math
import time
import urllib.request
import urllib.error
from compiler import NoRedirect,ModelError
from skill_selection import PROMPT,validate_catalog,validate_selection
from win_credentials import read_credential
from contracts import load_json,ContractError
from catalog_uniqueness import guard_selection

MODEL='jev-1.13.0'
ENDPOINT='https://api.typesafe.ai/v1/systemone'
CREDENTIAL='TypeSafe/Jev/closed-loop-gui-agent'
THRESHOLD=.90

def build_request(text,skills):
    validate_catalog(skills)
    if not isinstance(text,str) or not text.strip() or len(text)>500:raise ValueError('INVALID_TEXT')
    criteria={f'skill_{i}':dict(name=s['name'],goal=s['goal'],finalGoals=s['finalGoals'],meaning='Run exactly this immutable reviewed workflow, only when the full instruction permits it.') for i,s in enumerate(skills)}
    criteria['clarify']='Missing required targets, ambiguous skill or conflicting references. Do not invoke.'
    criteria['reject']='Unsupported request, negation, question, cancellation, schedule, condition or rule override. Do not invoke.'
    return dict(model=MODEL,state=dict(text=text,skills=skills),questions=dict(selection=dict(type='choice',instructions=PROMPT+' Choose one option, not JSON prose.',criteria=criteria)))

def probability(value):
    return type(value) in (int,float) and math.isfinite(value) and 0<=value<=1

def parse_selection(data,skills):
    validate_catalog(skills)
    try:
        if not isinstance(data,dict) or data.get('model')!=MODEL or set(data['answers'])!={'selection'}:raise ValueError('MODEL_OR_ANSWERS')
        answer=data['answers']['selection'];choice=answer['choice'];probs=answer['probabilities'];confidence=answer['confidence']
        options={f'skill_{i}' for i in range(len(skills))}|{'clarify','reject'}
        if answer['type']!='choice' or choice not in options or not probability(confidence):raise ValueError('ANSWER')
        if not isinstance(probs,dict) or set(probs)!=options or not all(probability(p) for p in probs.values()):raise ValueError('DISTRIBUTION')
        if abs(sum(probs.values())-1)>.02 or probs[choice]<max(probs.values()):raise ValueError('DISTRIBUTION')
        if choice in ('clarify','reject'):status=choice;identity=None
        elif probs[choice]>=THRESHOLD and confidence>=THRESHOLD:status='invoke';identity=skills[int(choice[6:])]['id']
        else:status='clarify';identity=None
        message={'invoke':'请核对这条技能，确认前不会执行。 / Review this skill; nothing has run.',
                 'clarify':'请补充明确的技能名称或完整目标。 / Specify a skill or complete targets.',
                 'reject':'该请求不在已审核技能范围内。 / Request outside reviewed skills.'}[status]
        return validate_selection(dict(status=status,skill_id=identity,message=message),skills)
    except (KeyError,TypeError,IndexError,AttributeError):raise ValueError('MALFORMED_JEV') from None

def remote(body):
    key=read_credential(CREDENTIAL,'utf-16-le')
    if not key.startswith('apikey_') or len(key)>2000:raise ModelError('INVALID_JEV_CREDENTIAL')
    req=urllib.request.Request(ENDPOINT,data=json.dumps(body,ensure_ascii=False).encode(),
        headers={'Content-Type':'application/json','Authorization':'Bearer '+key},method='POST')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=45) as reply:
            raw=reply.read(65537)
        if len(raw)>65536:raise ModelError('RESPONSE_SIZE')
        # Defend evidence logs even against an unexpected credential echo.
        return load_json(raw.decode('utf-8').replace(key,'[REDACTED]'))
    except urllib.error.HTTPError as e:raise ModelError('HTTP_'+str(e.code)) from None
    except (TimeoutError,urllib.error.URLError):raise ModelError('NETWORK_OR_TIMEOUT') from None
    except (UnicodeError,ContractError):raise ModelError('MALFORMED_RESPONSE') from None

def select_jev(text,skills,transport=remote):
    return guard_selection(text,skills,parse_selection(transport(build_request(text,skills)),skills))
