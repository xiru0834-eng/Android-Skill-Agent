"""Independent scorer. Private App journal is NEVER sent to the Agent/Flow runner."""
import argparse,copy,json,time,uuid
from pathlib import Path
from lab_transport import adb,execute
from prepare_g1 import save
ROOT=Path(__file__).parent
def oracle(host):return json.loads(adb(host,'shell','run-as','edu.sydney.parameterroom','cat','files/parameter-room-oracle.json'))
def prepare(host,case,initial=(0,50,0,22),fault='normal',delay=0):
    adb(host,'shell','am','start','-n','edu.sydney.parameterroom/.ParameterRoomActivity','--es','initial',','.join(map(str,initial)),
        '--es','caseId',case,'--es','fault',fault,'--ei','commitDelayMs',str(delay))
    deadline=time.monotonic()+4
    while time.monotonic()<deadline:
        try:before=oracle(host)
        except json.JSONDecodeError:
            # Evaluator journal replacement is not atomic in the unchanged test App.
            # Only initialization may wait for a parseable snapshot; never infer state.
            time.sleep(.05);continue
        if before['case_id']==case and before['initial']==list(initial) and not before['events']:return before
        time.sleep(.1)
    raise RuntimeError('INITIALIZATION_FAILED')
def assess(result,before,after,expected,events,allowed_success):
    actual=after['state'];ledger=[{'property':e['property'],'value':e['value']} for e in after['events']]
    success=result.get('final_status') in {'SUCCESS','NO_ACTION_REQUIRED'}
    truth=actual==expected and ledger==events
    wrong=any(e not in events for e in ledger) if allowed_success else bool(ledger)
    return {'passed':truth and success==allowed_success,'false_success':success and not truth,
            'wrong_action':wrong,'actual_state':actual,'actual_event_order':ledger,
            'state_preserved':all(actual[k]==before['state'][k] for k in actual if not any(e['property']==k for e in events))}
def run(host,out,smoke=False):
    if out.exists():raise RuntimeError('PRESERVE_OLD_BATCH')
    out.mkdir(parents=True);base=json.loads((ROOT/'evidence'/host/'g1-plan.json').read_text(encoding='utf-8'))
    cases=[('changed',base,(0,50,0,22),'normal',True,[80],None,True,None,0)]
    if not smoke:
        cases += [('already',base,(0,80,0,22),'normal',True,[],None,True,None,0),
                  ('missing_authority',base,(0,50,0,22),'normal',False,[],None,False,None,0),
                  ('unauthorized_write',base,(0,50,0,22),'normal',False,[],[],True,None,0),
                  ('missing_target',base,(0,50,0,22),'missing',False,[],None,True,None,0),
                  ('ambiguous',base,(0,50,0,22),'duplicate',False,[],None,True,None,0),
                  ('no_effect',base,(0,50,0,22),'stubborn',False,[80],None,True,None,0),
                  ('cancel_before_input',base,(0,50,0,22),'normal',False,[],None,True,.05,0),
                  ('delay_500',base,(0,50,0,22),'normal',True,[80],None,True,None,500)]
        invalid=copy.deepcopy(base)
        invalid['steps'].append(copy.deepcopy(base['steps'][1]));invalid['steps'][-1]['id']='illegal_later';invalid['steps'][-1]['value']['value']=101
        invalid['call_count']=2
        cases.append(('illegal_later',invalid,(0,50,0,22),'normal',False,[],None,True,None,0))
        ordered=copy.deepcopy(base);calls=[]
        for n,v in enumerate([20,50]):
            s=copy.deepcopy(base['steps'][1]);s['id']='ordered_'+str(n);s['value']['value']=v;s['call']['args']['percent']=v;calls.append(s)
        ordered['steps']=[base['steps'][0],*calls];ordered['goals'][0]['right']['value']=50;ordered['call_count']=2
        cases.append(('ordered_same_final',ordered,(0,50,0,22),'normal',True,[20,50],None,True,None,0))
    rows=[]
    for name,plan,initial,fault,success,values,writes,confirmed,cancel,delay in cases:
        cid=uuid.uuid4().hex;before=prepare(host,cid,initial,fault,delay)
        expected=copy.deepcopy(before['state']);events=[{'property':'bedroom_light.brightnessPercent','value':v} for v in values]
        if success and values:expected['bedroom_light.brightnessPercent']=values[-1]
        result=execute(host,plan,writes=writes,confirmed=confirmed,cancel_after=cancel)
        after=oracle(host)
        score=assess(result,before,after,expected,events,success)
        # Stubborn fixture deliberately journals an input but does not apply it.
        if name=='no_effect':score['wrong_action']=False
        row={'case':name,'host':host,'channel':'TEST_FIXTURE_REAL_ANDROID','before':before,'after':after,'result':result,'assessment':score}
        save(out/(name+'.json'),row);rows.append(row)
        print(name,result.get('final_status'),result.get('reason'),score['passed'],flush=True)
        if score['wrong_action'] or score['false_success']:break
    save(out/'summary.json',{'passed':sum(r['assessment']['passed'] for r in rows),'executed':len(rows),'planned':len(cases),
         'wrong_action':sum(r['assessment']['wrong_action'] for r in rows),'false_success':sum(r['assessment']['false_success'] for r in rows),'model_calls':0})
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--host',required=True);p.add_argument('--out',required=True);p.add_argument('--smoke',action='store_true');a=p.parse_args();run(a.host,Path(a.out),a.smoke)
