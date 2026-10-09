"""Deterministic software fixtures. Never present these as Android/model trials."""
import copy
from workflow_contract import compile_evidence
from task5_evidence import judge_run
from flexible_workflow import snapshot


def specimen():
    states=[dict(page='lamp',saved=[0,40,0,3],draft=[0,40,0,3]),
            dict(page='lamp',saved=[0,40,0,3],draft=[0,60,0,3]),
            dict(page='overview',saved=[0,60,0,3],draft=[0,60,0,3])]
    snapshots=[snapshot('overview',[0,40,0,3],[0,40,0,3])]+[snapshot(s['page'],s['saved'],s['draft']) for s in states]
    ids=['wfOpenLamp','wfLampValue60','wfLampSave']
    trace=dict(kind='WORKFLOW_TRACE',version=2,traceId='12345678-1234-1234-1234-123456789abc',appPackage='edu.sydney.transferlab',
        appVersion='6',source='AUTOMATED',goal='Software fixture only',end='STOPPED',error='',initial=snapshots[0],
        steps=[dict(id=k,before=snapshots[i],after=snapshots[i+1],eventTime=i+1,attribution='RESOURCE_ID') for i,k in enumerate(ids)],final=snapshots[-1])
    skill=compile_evidence(trace);initial=[0,40,0,3]
    oracle=dict(caseId='a'*16,initial=initial,events=[dict(ms=1,kind='initial',page='overview',saved=initial,draft=initial,pending=0)])
    journal=[dict(runId='software',seq=1,ms=10,kind='START',data=skill,stepIndex=0,phase=0)];actions=[]
    for i,state in enumerate(states,1):
        step=skill['steps'][i-1];at=i*100;actions.append(dict(ms=at,id=step['id'],sourceIndex=i))
        oracle['events'].append(dict(ms=at,kind=('edit:' if i==2 else 'input:')+step['id'],pending=0,**state))
        for kind,data,offset in [('INPUT_REQUEST',step,0),('INPUT_RETURN',dict(accepted=True,dispatchedMs=at,confirmationDeadlineMs=at+4000),1),
                ('CONFIRMATION_CHECK',dict(sourceIndex=i,observedMs=at+10,confirmationDeadlineMs=at+4000,taskDeadlineMs=30000),10),('STEP_CONFIRMED',step,11)]:
            journal.append(dict(runId='software',seq=len(journal)+1,ms=at+offset,kind=kind,data=data,stepIndex=i-1,phase=2))
    result=dict(runId='software',traceId=skill['traceId'],traceSha256=skill['traceSha256'],status='SUCCEEDED',reason='ORDERED_PROCESS_AND_TARGETS_VERIFIED',
        actions=actions,completedSteps=3,startedMs=10,finishedMs=400,deadlineMs=30000,terminalStepIndex=3)
    journal.append(dict(runId='software',seq=len(journal)+1,ms=400,kind='RESULT',data=copy.deepcopy(result),stepIndex=3,phase=3))
    samples=[]
    for ms in [500,1500,5500]:
        event=copy.deepcopy(oracle['events'][-1]);event.update(ms=ms,kind='audit_snapshot');oracle['events'].append(event);samples.append(copy.deepcopy(oracle))
    return [skill,initial,result,oracle,journal,samples,[0,60,0,3],'a'*16]


def experiment():
    rows=[];raw={}
    for family in ['normal','disk','late','source','non_target','old_audit','no_terminal']:
        for repeat in range(3):
            data=copy.deepcopy(specimen());value=[20,40,80][repeat]
            if family=='disk':data[6][1]=value
            elif family=='late':
                data[2]['deadlineMs']=397+repeat
                data[4][-1]['data']=copy.deepcopy(data[2])
                for event in data[4]:
                    if event['kind']=='CONFIRMATION_CHECK':event['data']['taskDeadlineMs']=data[2]['deadlineMs']
            elif family=='source':data[2]['actions'][repeat]['sourceIndex']=0
            elif family=='non_target':
                data[3]['events'][repeat+1]['draft'][2]=1
                # Keep prefix audits consistent so this isolates process protection.
                for audit in data[5]:audit['events'][repeat+1]['draft'][2]=1
            elif family=='old_audit':data[5]=[data[5][repeat]]*3
            elif family=='no_terminal':data[4].pop()
            key=f'{family}-r{repeat}';checked=judge_run(data);wanted='PASS' if family=='normal' else ('UNVERIFIED' if family in ['source','old_audit','no_terminal'] else 'FAIL')
            rows.append(dict(id=key,family=family,repeat=repeat,expected=wanted,actual=checked['state'],matches=checked['state']==wanted,
                errors=checked['errors'],falseSuccess=checked['falseSuccess'],evidenceLevel='SOFTWARE_SYNTHETIC_NOT_ANDROID'))
            raw[key]=data
    return dict(rows=rows,raw=raw,n=len(rows),matches=sum(r['matches'] for r in rows),scope='Adjudicator sensitivity, not runtime ablation benefits')
