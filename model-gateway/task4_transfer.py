"""Transfer boundary proof and safe-stop scoring, independent of Android operator."""
import json
import xml.etree.ElementTree as ET
from task4_protocol import package_bytes,fingerprint,canonical
from task3_audit import rejudge
from flexible_device_checks import expected_process_states


def chain_check(expected,p):
    errors=[]
    def check(ok,reason):
        if not ok:errors.append(reason)
    try:
        check(p['sourceAvd']=='Task3Workflows' and p['targetAvd']=='Task4Transfer','AVD_IDENTITY')
        package_bytes(p['sourceBlob'],expected);package_bytes(p['targetBlob'],expected)
        check(p['sourceBlob']==p['targetBlob'],'BYTES_CHANGED')
        check(p['sourceBefore']==p['sourceAfter'],'SOURCE_STATE_CHANGED')
        check(p['pending'].get('storageUnconfirmed')!='true' and p['after'].get('storageUnconfirmed')!='true','STORAGE_UNCONFIRMED')
        check(all(p['pending'].get(k)==p['before'].get(k) for k in ['approved','library','result','draft']),'PENDING_CHANGED_APPROVAL_OR_TASK')
        check(canonical(json.loads(p['pending']['pendingNamed']))==canonical(expected),'PENDING_DIFFERS')
        check('pendingNamed' not in p['after'] and canonical(json.loads(p['after']['approved']))==canonical(expected['skill']),'LOCAL_REVIEW_MISSING')
        check(sum(canonical(e)==canonical(expected) for e in json.loads(p['after']['library']))==1,'REVIEWED_PACKAGE_NOT_UNIQUE')
        check(all(e in json.loads(p['after']['library']) for e in json.loads(p['before'].get('library','[]'))),'OLD_LIBRARY_CHANGED')
        check(p['after'].get('result')==p['before'].get('result') and p['after'].get('draft')==p['before'].get('draft'),'REVIEW_CHANGED_TASK_OR_DRAFT')
        for key,marker in [('exportXml','Skill exported.'),('importXml','Import draft:'),('reviewXml','android:id/button1')]:
            ui=ET.fromstring(p[key]);values=[value for n in ui.iter() for value in n.attrib.values()]
            check(any(marker in value for value in values),'MISSING_UI_ACK:'+key)
    except (KeyError,TypeError,ValueError,ET.ParseError):errors.append('INCOMPLETE_CHAIN_EVIDENCE')
    return dict(correctChain=not errors,evidenceQualified=not errors,errors=errors,
        sourceSha256=fingerprint(p['sourceBlob']) if type(p.get('sourceBlob')) is bytes else None,
        targetSha256=fingerprint(p['targetBlob']) if type(p.get('targetBlob')) is bytes else None,paidCalls=0)


def restore_commands(state):
    size='x'.join(map(str,state['overrideSize'])) if state['overrideSize'] else 'reset'
    density=str(state['overrideDensity']) if state['overrideDensity'] else 'reset'
    font=['settings','delete','system','font_scale'] if state['fontRaw']=='null' else ['settings','put','system','font_scale',state['fontRaw']]
    return [['wm','size',size],['wm','density',density],font]


def fault_trigger(fault,ui):
    prefix='edu.sydney.transferlab:id/'
    pages=[n.get('text') for n in ui.iter('node') if n.get('resource-id')==prefix+'wfPage']
    if len(pages)!=1:return False
    ids=[n.get('resource-id') for n in ui.iter('node')]
    if fault=='missing':return pages[0] in ['single','fan'] and ids.count(prefix+'wfFanSave')==0 and ids.count(prefix+'wfFanCancel')==1 and ids.count(prefix+'wfFanPower')==1
    if fault=='duplicate':return pages[0] in ['single','lamp'] and ids.count(prefix+'wfLampPower')==2
    raise ValueError('UNKNOWN_FAULT')


def fault_score(row,skill,initial,result,oracle,journal,samples,disk,case_id,ui):
    base=rejudge(skill,initial,result,oracle,journal,samples,disk,case_id)
    errors=[e for e in base['errors'] if e!='PROCESS_OR_FINAL_MISMATCH']
    def check(ok,reason):
        if not ok:errors.append(reason)
    fault=row['fault'];index=0 if fault=='duplicate' else {'S3':5,'M1':7,'M4':6}[row['flow']]
    reason='AMBIGUOUS:wfLampPower' if fault=='duplicate' else 'MISSING:wfFanSave'
    trigger=fault_trigger(fault,ui) and oracle['fault']==fault
    check(trigger,'FAULT_NOT_PROVEN')
    check(result.get('status')=='UNCONFIRMED' and result.get('reason')==reason,'WRONG_SAFE_TERMINAL')
    check(result.get('terminalStepIndex')==index and result.get('completedSteps')==index,'WRONG_STOP_INDEX')
    confirmed=[e for e in journal if e['kind']=='STEP_CONFIRMED']
    check([e['data']['sourceIndex'] for e in confirmed]==list(range(1,index+1)),'CONFIRMED_PREFIX_DIFFERS')
    expected=expected_process_states(skill,initial)
    for entry in confirmed:
        n=entry['data']['sourceIndex']-1;at=[e for e in oracle['events'] if e['ms']<=entry['ms']]
        check(bool(at) and all(at[-1][k]==expected[n][k] for k in ['page','saved','draft']) and at[-1]['pending']==0,'WRONG_CONFIRMED_PREFIX')
    observed=[e['kind'].split(':',1)[1] for e in oracle['events'] if e['kind'].startswith(('input:','edit:'))]
    check(observed==[a['id'] for a in result['actions']],'INPUTS_DIFFER_FROM_LEDGER')
    check(all(a['sourceIndex']<=index+1 for a in result['actions']),'INPUT_AFTER_FAILED_STEP')
    if fault=='duplicate':
        allowed=[] if row['flow']=='S3' else ['wfOpenLamp']
        check(observed==allowed,'AMBIGUOUS_TARGET_RECEIVED_INPUT')
    qualified=base['evidenceQualified'] and trigger
    return dict(safeStop=not errors,evidenceQualified=qualified,errors=errors,normalCompletion=False,
        falseSuccess=base['falseSuccess'],elapsedMs=base['elapsedMs'],reason=result.get('reason'))
