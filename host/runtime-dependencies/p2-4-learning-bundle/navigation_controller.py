"""Scoped public-UI navigation recorder. No private state/hidden locators/test answer imports.
It records a requested demonstrated route, not P3 autonomous App exploration.
"""
import time
import uuid
from bundle_contract import need
from native_materials import validate_native_observation

def observe(bridge,*,wait_ready=True):
    # Bounded initialization/re-observation; no input retry and no renewed task budget.
    deadline=time.monotonic()+8;last='CAPTURE_ERROR'
    for attempt in range(3):
        r=bridge.observe();last=r.get('error','CAPTURE_ERROR')
        if r['status']=='COLLECTED':
            o=validate_native_observation(r['observation'])
            waiting=any(n['resource_id']==o['app_package']+':id/wfReady' and n['text'] in {'Waiting','Waiting / 正在提交或跳转'} for n in o['tree']['nodes'])
            if not wait_ready or not waiting:return o
            last='UI_NOT_READY'
        if last not in {'WINDOW_MISMATCH','ROOT_UNAVAILABLE','OBSERVATION_INCONSISTENT','UI_NOT_READY','TREE_API_ERROR'}:break
        if time.monotonic()>=deadline:break
        time.sleep(min(.2,max(0,deadline-time.monotonic())))
    need(False,last)

def candidate(observation,public_text):
    choices=[n for n in observation['tree']['nodes'] if n['visible'] and n['enabled'] and n['clickable']
             and public_text.casefold() in (n['text'] or n['content_description'] or '').casefold()]
    need(len(choices)==1,'AMBIGUOUS' if choices else 'NOT_FOUND');return choices[0]

def navigate(bridge,before,public_text):
    target=candidate(before,public_text);dispatch=bridge.click(before,target)
    need(dispatch['status']=='DISPATCHED',dispatch.get('error','DISPATCH_FAILED'))
    # No action retry. After dispatch, observe actual current UI and event metadata.
    after=observe(bridge);events=bridge.events();need(events['status']=='EVENTS','EVENTS_UNAVAILABLE')
    return {'interaction_id':str(uuid.uuid4()),'actor':'AGENT_NAVIGATION','before':before,
            'dispatch':dispatch['dispatch'],'after':after,'events':events['event_record']['events'],
            'business_audit':None,'status':'ARRIVAL_VERIFIED'}
