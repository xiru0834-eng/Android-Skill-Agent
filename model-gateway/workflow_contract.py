"""A narrow evidence compiler: two demonstrated device groups, not arbitrary GUI code."""
import hashlib
import json
import uuid
from workflow_score import valid_values

class WorkflowError(ValueError): pass

def need(ok, reason):
    if not ok: raise WorkflowError(reason)

def canonical(value): return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def snapshot(value):
    need(type(value) is dict and set(value)=={'page','values','saved','dirty'},'SNAPSHOT_FIELDS')
    need(value['page'] in ('overview','lamp','fan') and type(value['dirty']) is bool,'PAGE')
    need(type(value['values']) is dict and len(value['values'])<=16,'VALUES')
    import re
    for key,val in value['values'].items():
        need(re.fullmatch(r'wf(?:Lamp|Fan)(?:Power|Value(?:20|40|60|80|100|1|2|3))',key) and type(val) is bool,'CONTROL')
    need(value['saved']==[] or valid_values(value['saved']),'SAVED_VALUES')
    if value['page']=='overview':need(valid_values(value['saved']) and not value['values'],'OVERVIEW')
    else:need(value['saved']==[],'DETAIL')

def compile_evidence(trace):
    if type(trace) is dict and type(trace.get('version')) is int and trace['version']==2:
        from flexible_workflow import compile_flexible
        return compile_flexible(trace)
    fields={'kind','version','traceId','appPackage','appVersion','source','goal','end','error','initial','steps','final'}
    need(type(trace) is dict and set(trace)==fields,'TRACE_FIELDS')
    need(trace['kind']=='WORKFLOW_TRACE' and type(trace['version']) is int and trace['version']==1,'VERSION')
    need(trace['appPackage']=='edu.sydney.transferlab','APP')
    try: need(str(uuid.UUID(trace['traceId']))==trace['traceId'],'TRACE_ID')
    except (ValueError,TypeError,AttributeError):raise WorkflowError('TRACE_ID') from None
    need(trace['source'] in ('AUTOMATED','HUMAN_DECLARED'),'SOURCE')
    need(trace['end']=='STOPPED' and trace['error']=='','INCOMPLETE_TRACE')
    need(type(trace['goal']) is str and 0<len(trace['goal'])<=240,'GOAL')
    need(type(trace['appVersion']) is str and trace['appVersion'].isdigit(),'APP_VERSION')
    snapshot(trace['initial']);snapshot(trace['final'])
    need(trace['initial']['page']=='overview' and trace['final']['page']=='overview','START_END')
    need(not trace['initial']['dirty'] and not trace['final']['dirty'],'UNSAVED')
    steps=trace['steps'];need(type(steps) is list and len(steps) in (4,8),'FOUR_OR_EIGHT_VERIFIED_STEPS_REQUIRED')
    previous=trace['initial'];last_time=-1;out=[];goals=list(trace['initial']['saved']);groups=set()
    for offset in range(0,len(steps),4):
        entry=steps[offset];need(type(entry) is dict,'STEP')
        group={'wfOpenLamp':('Lamp','lamp',0),'wfOpenFan':('Fan','fan',2)}.get(entry.get('id'))
        need(group is not None and group[0] not in groups,'GROUP_ROUTE');title,page,index=group;groups.add(title)
        expected_ids=['wfOpen'+title,'wf'+title+'Power',None,'wf'+title+'Save']
        for pos in range(4):
            step=steps[offset+pos]
            need(type(step) is dict and set(step)=={'id','before','after','eventTime','attribution'},'STEP_FIELDS')
            snapshot(step['before']);snapshot(step['after'])
            need(step['before']==previous,'DISCONTINUOUS_TRACE')
            need(type(step['eventTime']) is int and last_time<step['eventTime'],'EVENT_ORDER');last_time=step['eventTime']
            need(step['attribution'] in ('RESOURCE_ID','UNIQUE_LABEL'),'ATTRIBUTION')
            expected_before='overview' if pos==0 else page;expected_after='overview' if pos==3 else page
            need(step['before']['page']==expected_before and step['after']['page']==expected_after,'ROUTE')
            key=step['id'];desired=None
            if pos==2:
                prefix='wf'+title+'Value';need(type(key) is str and key.startswith(prefix),'VALUE_ID')
                suffix=key[len(prefix):];need(suffix in ([str(v) for v in (20,40,60,80,100)] if index==0 else ['1','2','3']),'VALUE')
                goals[index+1]=int(suffix)
            else:need(key==expected_ids[pos],'ACTION_ID')
            if pos in (1,2):
                need(step['before']['values'].get(key) is False if pos==2 else type(step['before']['values'].get(key)) is bool,'BEFORE_VALUE')
                desired=step['after']['values'].get(key);need(type(desired) is bool,'AFTER_VALUE')
                need(desired!=step['before']['values'].get(key) and (pos!=2 or desired),'NO_OBSERVED_CHANGE')
                if pos==1:goals[index]=int(desired)
            if pos==3:need(step['after']['saved']==goals and not step['after']['dirty'],'COMMIT_MISMATCH')
            out.append(dict(id=key,page=expected_before,afterPage=expected_after,desired=desired,sourceIndex=offset+pos+1))
            previous=step['after']
    need(previous==trace['final'] and trace['final']['saved']==goals,'FINAL_MISMATCH')
    if len(steps)==4:
        untouched=2 if 'Lamp' in groups else 0
        goals[untouched:untouched+2]=[None,None]
    return dict(kind='WORKFLOW_SKILL',version=2 if len(steps)==4 else 1,appPackage=trace['appPackage'],appVersion=trace['appVersion'],
                traceId=trace['traceId'],traceSha256=hashlib.sha256(canonical(trace).encode()).hexdigest(),
                source=trace['source'],goal=trace['goal'],steps=out,finalGoals=goals)

def validate_proposal(proposal, count):
    need(type(proposal) is dict and set(proposal)=={'status','reason','indices'},'MODEL_FIELDS')
    need(proposal['status'] in ('candidate','clarify','reject'),'MODEL_STATUS')
    need(type(proposal['reason']) is str and 0<len(proposal['reason'])<=500,'MODEL_REASON')
    need(type(proposal['indices']) is list and all(type(i) is int for i in proposal['indices']),'MODEL_INDICES')
    need(proposal['indices']==(list(range(1,count+1)) if proposal['status']=='candidate' else []),'MODEL_CHANGED_STEPS')
