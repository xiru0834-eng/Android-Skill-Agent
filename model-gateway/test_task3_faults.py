"""Safe-stop scorer tests with synthetic evidence; not device fault results."""
import copy
import unittest
from test_task3_workflows import sample
from task3_faults import safe_stop


def dropped():
    data=list(copy.deepcopy(sample()));skill=data[0]
    # Use this three-step fixture's dropped save; save remains the unconfirmed step.
    result=data[2];journal=data[4]
    result.update(status='UNCONFIRMED',reason='STEP_UNCONFIRMED',completedSteps=2,terminalStepIndex=2)
    journal[:]=[e for e in journal if not(e['kind']=='STEP_CONFIRMED' and e['data']['sourceIndex']==3)]
    journal[-1]['data']=copy.deepcopy(result)
    for n,e in enumerate(journal,1):e['seq']=n
    event=data[3]['events'][-1];event.update(page='lamp',saved=[0,40,0,3],draft=[0,60,0,3])
    data[5]=[]
    for ms in [500,1500,5500]:
        audit=copy.deepcopy(event);audit.update(ms=ms,kind='audit_snapshot')
        data[3]['events'].append(audit);data[5].append(copy.deepcopy(data[3]))
    data[6]=[0,40,0,3]
    return data


class FaultTests(unittest.TestCase):
    def test_proven_dropped_save_is_safe_stop_not_completion(self):
        checked=safe_stop('save_drop',*dropped(),True)
        self.assertTrue(checked['safeStop'],checked['errors']);self.assertFalse(checked['normalCompletion'])
    def test_trigger_wrong_reason_and_post_terminal_input_rejected(self):
        for mutation in ['trigger','reason','late_input','confirmed_wrong','missing_receipt','success']:
            data=dropped();trigger=True
            if mutation=='trigger':trigger=False
            elif mutation=='reason':data[2]['reason']='WRONG_PAGE'
            elif mutation=='late_input':data[2]['actions'][-1]['ms']=500
            elif mutation=='confirmed_wrong':data[3]['events'][1]['draft'][1]=60
            elif mutation=='missing_receipt':data[4][:]=[e for e in data[4] if e['kind']!='INPUT_RETURN']
            else:data[2]['status']='SUCCEEDED'
            with self.subTest(mutation=mutation):self.assertFalse(safe_stop('save_drop',*data,trigger)['safeStop'])
    def test_a_missing_fresh_audit_cannot_pass_as_safe_stop(self):
        data=dropped();data[5].pop(0)
        self.assertFalse(safe_stop('save_drop',*data,True)['safeStop'])


if __name__=='__main__':unittest.main()
