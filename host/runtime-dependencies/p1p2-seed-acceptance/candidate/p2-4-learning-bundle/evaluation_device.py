"""Independent test-state audit, NEVER imported by navigation_controller or learning_queries.
Only the evaluator reads the existing experiment App's real event ledger.
"""
import json
import subprocess
import time
from android_bridge import ADB,SERIALS

def adb(serial,*args):
    if serial not in SERIALS:raise ValueError('UNKNOWN_HOST')
    r=subprocess.run([str(ADB),'-s',serial,*args],capture_output=True,timeout=20)
    if r.returncode:raise RuntimeError('EVALUATOR_ADB_ERROR')
    return r.stdout

def read_business(serial):
    r=subprocess.run([str(ADB),'-s',serial,'shell','run-as','edu.sydney.transferlab','cat','files/workflow-oracle.json'],capture_output=True,timeout=15)
    if r.returncode:return None
    return json.loads(r.stdout)

def state(snapshot):
    if snapshot is None:return None
    events=snapshot.get('events');
    if not events:raise RuntimeError('REAL_STATE_UNAVAILABLE')
    last=events[-1]
    return {'saved':last['saved'],'draft':last['draft'],'pending':last['pending']}

def check_clean(snapshot):
    s=state(snapshot)
    if s is not None and (s['saved']!=s['draft'] or s['pending']!=0):raise RuntimeError('EXISTING_UNSAVED_WORK_BLOCKED')

def audit_delta(before,after):
    if before is None or after is None:raise RuntimeError('INDEPENDENT_STATE_UNAVAILABLE')
    a,b=state(before),state(after);prefix=before['events'];events=after['events']
    if after['caseId']!=before['caseId'] or events[:len(prefix)]!=prefix:raise RuntimeError('BUSINESS_LEDGER_CHANGED')
    new=events[len(prefix):]
    safe_inputs={'input:wfOpenLamp','input:wfOpenFan','input:wfLampBack','input:wfFanBack'}
    writing=[e for e in new if e['kind'].startswith(('edit:','save','cancel','dropped_save','rollback'))
             or e['kind'].startswith('input:') and e['kind'] not in safe_inputs]
    return {'write_count':len(writing),'pending_count':b['pending'],
            'state_unchanged':a['saved']==b['saved'] and a['draft']==b['draft'],
            'event_count':len(new),'event_kinds':[e['kind'] for e in new],
            'source':'INDEPENDENT_EXISTING_APP_EVENT_LEDGER'}

def foreground(serial,*,layout='multi'):
    # setup is evaluator work, not counted as Agent navigation or autonomous learning.
    if layout not in {'multi','single'}:raise ValueError('INVALID_LAYOUT')
    return adb(serial,'shell','am','start','-n','edu.sydney.transferlab/.WorkflowActivity','--es','layout',layout).decode('utf-8')

def prepare(serial,values,*,layout='multi',fault='normal'):
    import uuid
    if layout not in {'multi','single'} or fault not in {'normal','navdelay'}:raise ValueError('INVALID_EVALUATOR_CONFIG')
    if (type(values) is not list or len(values)!=4 or any(type(v) is not int for v in values)
        or values[0] not in [0,1] or values[2] not in [0,1]
        or values[1] not in [20,40,60,80,100] or values[3] not in [1,2,3]):raise ValueError('INVALID_EVALUATOR_STATE')
    case_id=uuid.uuid4().hex[:16]
    result=adb(serial,'shell','am','start','-n','edu.sydney.transferlab/.WorkflowActivity',
        '--es','layout',layout,'--es','initial',','.join(map(str,values)),'--es','caseId',case_id,
        '--es','fault',fault).decode('utf-8')
    # am start may return before onNewIntent writes the new evaluator ledger.
    # Same values alone cannot identify the current run. This private receipt is
    # never supplied to the navigation controller or readonly queries.
    deadline=time.monotonic()+3.0
    while time.monotonic()<deadline:
        snapshot=read_business(serial)
        if snapshot is not None and snapshot.get('caseId')==case_id:
            current=state(snapshot)
            if (snapshot.get('layout')==layout and snapshot.get('fault')==fault
                and snapshot.get('initial')==values and current['saved']==values
                and current['draft']==values and type(current['pending']) is int and current['pending']==0):
                return result
        time.sleep(.05)
    raise RuntimeError('INITIALIZATION_UNCONFIRMED')
