"""Ordered, variable-length evidence compilation for the existing lab primitives."""
import hashlib
import uuid
from workflow_contract import need, canonical

OPTIONS=((0,1),(20,40,60,80,100),(0,1),(1,2,3))

def valid_goals(values, partial=False):
    return (type(values) is list and len(values)==4 and
            all((v is None and partial) or (type(v) is int and v in OPTIONS[i]) for i,v in enumerate(values)))

def values_for(page, draft):
    values={}
    for group,i in (('Lamp',0),('Fan',2)):
        if page not in ('single',group.lower()):continue
        values['wf'+group+'Power']=bool(draft[i])
        for v in OPTIONS[i+1]:values['wf'+group+'Value'+str(v)]=draft[i+1]==v
    return values

def snapshot(page, saved, draft):
    indices=range(4) if page in ('overview','single') else range(0,2) if page=='lamp' else range(2,4)
    return dict(page=page,values=values_for(page,draft),saved=saved.copy() if page in ('overview','single') else [],
                dirty=any(saved[i]!=draft[i] for i in indices))

def check_snapshot(s):
    need(type(s) is dict and set(s)=={'page','values','saved','dirty'},'SNAPSHOT_FIELDS')
    need(s['page'] in ('overview','single','lamp','fan') and type(s['dirty']) is bool,'PAGE')
    need(type(s['values']) is dict and all(type(v) is bool for v in s['values'].values()),'VALUES')
    need(valid_goals(s['saved']) if s['page'] in ('overview','single') else s['saved']==[],'SAVED_VALUES')

def action(key,page,desired):
    need(type(key) is str,'ACTION_ID')
    if key in ('wfSingle','wfMulti','wfOpenLamp','wfOpenFan'):
        before='overview' if key in ('wfSingle','wfOpenLamp','wfOpenFan') else 'single'
        after={'wfSingle':'single','wfMulti':'overview','wfOpenLamp':'lamp','wfOpenFan':'fan'}[key]
        need(page==before and desired is None,'ROUTE')
        return 'NAVIGATE',after,None,None
    for group,i in (('Lamp',0),('Fan',2)):
        if not key.startswith('wf'+group):continue
        need(page in ('single',group.lower()),'WRONG_PAGE')
        suffix=key[len('wf'+group):]
        if suffix=='Power':
            need(type(desired) is bool,'DESIRED');return 'SET',page,i,int(desired)
        if suffix.startswith('Value') and suffix[5:] in tuple(map(str,OPTIONS[i+1])):
            need(desired is True,'DESIRED');return 'SET',page,i+1,int(suffix[5:])
        need(desired is None,'DESIRED')
        if suffix in ('Save','Cancel'):return suffix.upper(),'single' if page=='single' else 'overview',i,None
        if suffix=='Back':
            need(page==group.lower(),'ROUTE');return 'NAVIGATE','overview',i,None
    need(False,'UNSUPPORTED_ACTION')

def advance(page,saved,draft,intent,goals,key,after):
    saved=saved.copy();draft=draft.copy();intent=intent.copy();goals=goals.copy()
    desired=after['values'].get(key) if type(key) is str and ('Power' in key or 'Value' in key) else None
    op,after_page,field,value=action(key,page,desired);commit=[None]*4
    if op=='SET':
        if key.endswith('Power'):need(draft[field]!=value,'NO_OBSERVED_CHANGE')
        draft[field]=value;intent[field]=value
    elif op=='SAVE':
        for i in (field,field+1):
            saved[i]=draft[i];commit[i]=intent[i]
            if intent[i] is not None:goals[i]=intent[i]
            intent[i]=None
    elif op=='CANCEL':
        for i in (field,field+1):draft[i]=saved[i];intent[i]=None
    else:
        checked=range(4) if field is None else (field,field+1)
        need(all(draft[i]==saved[i] for i in checked),'UNSAVED_NAVIGATION')
    return after_page,saved,draft,intent,goals,op,desired,commit

def resolve(page,saved,draft,intent,goals,candidates,after):
    need(type(candidates) is list and 2<=len(candidates)<=16 and all(type(c) is str for c in candidates)
         and len(set(candidates))==len(candidates),'CANDIDATES')
    found=[]
    for key in candidates:
        desired=after['values'].get(key) if 'Power' in key or 'Value' in key else None
        action(key,page,desired)  # Every candidate must be an allowed primitive on this page.
        if key.endswith('Power') and values_for(page,draft).get(key)==desired:continue
        result=advance(page,saved,draft,intent,goals,key,after)
        if snapshot(result[0],result[1],result[2])==after:found.append(key)
    need(len(found)==1,'AMBIGUOUS_TRANSITION');return found[0]

def compile_flexible(trace):
    need(set(trace)=={'kind','version','traceId','appPackage','appVersion','source','goal','end','error','initial','steps','final'},'TRACE_FIELDS')
    need(trace['kind']=='WORKFLOW_TRACE' and trace['appPackage']=='edu.sydney.transferlab','APP')
    try:need(type(trace['traceId']) is str and str(uuid.UUID(trace['traceId']))==trace['traceId'],'TRACE_ID')
    except (ValueError,TypeError,AttributeError):need(False,'TRACE_ID')
    need(type(trace['appVersion']) is str and trace['appVersion'].isascii() and trace['appVersion'].isdigit() and len(trace['appVersion'])<=12,'APP_VERSION')
    need(trace['source'] in ('AUTOMATED','HUMAN_DECLARED'),'SOURCE')
    goal=trace['goal']
    need(type(goal) is str and bool(goal.strip()) and sum(2 if ord(c)>0xffff else 1 for c in goal)<=240
         and not any(0xd800<=ord(c)<=0xdfff for c in goal),'GOAL')
    need(trace['end']=='STOPPED' and trace['error']=='','INCOMPLETE_TRACE')
    need(len(canonical(trace).encode('utf-8'))<=262144,'EVIDENCE_SIZE')
    check_snapshot(trace['initial']);check_snapshot(trace['final'])
    page=trace['initial']['page'];start_page=page
    need(page in ('overview','single') and not trace['initial']['dirty'],'START')
    saved=trace['initial']['saved'].copy();draft=saved.copy()
    need(trace['initial']==snapshot(page,saved,draft),'INITIAL_MISMATCH')
    need(type(trace['steps']) is list and bool(trace['steps']),'NO_STEPS')
    intent=[None]*4;goals=[None]*4;out=[];last_time=-1
    for n,s in enumerate(trace['steps'],1):
        inferred=type(s) is dict and s.get('attribution')=='UNIQUE_TRANSITION'
        fields={'id','before','after','eventTime','attribution'}|({'candidateIds'} if inferred else set())
        need(type(s) is dict and set(s)==fields,'STEP_FIELDS')
        check_snapshot(s['before']);check_snapshot(s['after'])
        need(type(s['eventTime']) is int and last_time<s['eventTime']<=9223372036854775807,'EVENT_ORDER');last_time=s['eventTime']
        need(s['attribution'] in ('RESOURCE_ID','UNIQUE_LABEL','UNIQUE_TRANSITION'),'ATTRIBUTION')
        need(s['before']==snapshot(page,saved,draft),'DISCONTINUOUS_TRACE')
        key=s['id']
        if inferred:need(resolve(page,saved,draft,intent,goals,s['candidateIds'],s['after'])==key,'AMBIGUOUS_TRANSITION')
        before_page=page
        page,saved,draft,intent,goals,op,desired,commit=advance(page,saved,draft,intent,goals,key,s['after'])
        need(s['after']==snapshot(page,saved,draft),'ACTION_EFFECT_MISMATCH')
        out.append(dict(id=key,page=before_page,afterPage=page,desired=desired,sourceIndex=n,operation=op,commitGoals=commit))
    need(page in ('overview','single') and saved==draft and trace['final']==snapshot(page,saved,draft),'UNSAVED_OR_FINAL_MISMATCH')
    need(any(v is not None for v in goals),'NO_SAVED_TARGET')
    return dict(kind='WORKFLOW_SKILL',version=3,appPackage=trace['appPackage'],appVersion=trace['appVersion'],
                traceId=trace['traceId'],traceSha256=hashlib.sha256(canonical(trace).encode()).hexdigest(),
                source=trace['source'],goal=trace['goal'],startPage=start_page,endPage=page,steps=out,finalGoals=goals)
