"""Task 3 denominator and independent evidence checks, not model benchmarks."""
import copy
import unittest
from task3_protocol import FLOWS, cases, summary, judge
from workflow_contract import compile_evidence
from test_flexible_workflow import trace
from flexible_device_checks import expected_process_states


def sample():
    skill=compile_evidence(trace(['wfOpenLamp','wfLampValue60','wfLampSave']))
    initial=[0,40,0,3];states=expected_process_states(skill,initial)
    oracle=dict(caseId='a'*16,initial=initial,events=[dict(ms=1,kind='initial',page='overview',saved=initial,draft=initial,pending=0)])
    journal=[dict(runId='run',seq=1,ms=10,kind='START',data=skill,stepIndex=0,phase=0)]
    actions=[]
    for n,state in enumerate(states,1):
        step=skill['steps'][n-1];when=n*100
        actions.append(dict(ms=when,id=step['id'],sourceIndex=n))
        oracle['events'].append(dict(ms=when,kind=('edit:' if step['operation']=='SET' else 'input:')+step['id'],pending=0,**{k:v for k,v in state.items() if k!='operation'}))
        for kind,data,offset in [('INPUT_REQUEST',step,0),('INPUT_RETURN',dict(accepted=True,dispatchedMs=when,confirmationDeadlineMs=when+4000),1),
                                 ('CONFIRMATION_CHECK',dict(sourceIndex=n,observedMs=when+10,confirmationDeadlineMs=when+4000,taskDeadlineMs=30000),10),('STEP_CONFIRMED',step,11)]:
            journal.append(dict(runId='run',seq=len(journal)+1,ms=when+offset,kind=kind,data=data,stepIndex=n-1,phase=2))
    result=dict(runId='run',traceId=skill['traceId'],traceSha256=skill['traceSha256'],status='SUCCEEDED',reason='ORDERED_PROCESS_AND_TARGETS_VERIFIED',
                actions=actions,completedSteps=3,startedMs=10,finishedMs=400,deadlineMs=30000,terminalStepIndex=3)
    journal.append(dict(runId='run',seq=len(journal)+1,ms=400,kind='RESULT',data=copy.deepcopy(result),stepIndex=3,phase=3))
    samples=[copy.deepcopy(oracle),copy.deepcopy(oracle)];disk=oracle['events'][-1]['saved'].copy()
    return skill,initial,result,oracle,journal,samples,disk,'a'*16


class Task3Tests(unittest.TestCase):
    def test_fixed_denominators_and_unique_cases(self):
        plan=cases();self.assertEqual(len(plan),168)
        self.assertEqual(len({c['id'] for c in plan}),168)
        self.assertEqual({g:sum(c['group']==g for c in plan) for g in ['single','multi','fault','challenge']},dict(single=54,multi=72,fault=36,challenge=6))
    def test_all_twelve_flows_compile_and_long_process_not_collapsed(self):
        for name,flow in FLOWS.items():
            with self.subTest(name=name):
                s=compile_evidence(trace(flow['actions'],flow['page']))
                self.assertEqual(len(s['steps']),len(flow['actions']))
                self.assertEqual(s['startPage'],s['endPage'])
        self.assertEqual(len(FLOWS['M6']['actions']),22)
    def test_unrun_rows_remain_in_denominator(self):
        result=summary([])
        self.assertEqual(result['groups']['single']['NOT_RUN'],54)
        self.assertEqual(result['verdict'],'NOT_READY')
    def test_unknown_or_duplicate_rows_and_unproven_pass_rejected(self):
        for rows in [[dict(id='foreign',status='PASS')],[dict(id=cases()[0]['id'],status='PASS')],
                     [dict(id=cases()[0]['id'],status='NOT_RUN')]*2]:
            with self.subTest(rows=rows),self.assertRaises(ValueError):summary(rows)
    def test_complete_evidence_can_pass(self):
        self.assertTrue(judge(*sample())['correctCompletion'])
    def test_running_receipt_is_not_a_second_terminal(self):
        data=list(copy.deepcopy(sample()));journal=data[4]
        running=copy.deepcopy(data[2]);running.update(status='RUNNING',reason='STARTING',finishedMs=11,actions=[],completedSteps=0)
        journal.insert(1,dict(runId='run',seq=2,ms=12,kind='RESULT',data=running,stepIndex=0,phase=0))
        for n,e in enumerate(journal,1):e['seq']=n
        self.assertTrue(judge(*data)['correctCompletion'])
        journal.insert(-1,copy.deepcopy(journal[-1]))
        for n,e in enumerate(journal,1):e['seq']=n
        self.assertFalse(judge(*data)['correctCompletion'])
    def test_final_only_cannot_hide_missing_confirmation_or_wrong_intermediate(self):
        for mutation in ['remove','state','commit','metadata']:
            data=list(copy.deepcopy(sample()));j=data[4]
            if mutation=='remove':j[:]=[e for e in j if not(e['kind']=='STEP_CONFIRMED' and e['data']['sourceIndex']==2)]
            elif mutation=='state':data[3]['events'][2]['draft'][0]=1
            elif mutation=='commit':data[3]['events'][1]['saved'][1]=60
            else:next(e for e in j if e['kind']=='STEP_CONFIRMED')['data']['id']='wfOpenFan'
            with self.subTest(mutation=mutation):self.assertFalse(judge(*data)['correctCompletion'])
    def test_identity_order_and_terminal_inputs_rejected(self):
        for mutation in ['run','trace','hash','seq','clock','after_terminal','result']:
            data=list(copy.deepcopy(sample()));j=data[4];r=data[2]
            if mutation=='run':j[1]['runId']='other'
            elif mutation=='trace':r['traceId']='other'
            elif mutation=='hash':r['traceSha256']='0'*64
            elif mutation=='seq':j[1]['seq']=99
            elif mutation=='clock':j[2]['ms']=0
            elif mutation=='result':j[-1]['data']['status']='CANCELLED'
            else:r['actions'][-1]['ms']=500
            with self.subTest(mutation=mutation):self.assertFalse(judge(*data)['correctCompletion'])
    def test_late_receipt_rejected_even_when_state_and_terminal_success_match(self):
        data=list(copy.deepcopy(sample()));receipt=next(e for e in data[4] if e['kind']=='CONFIRMATION_CHECK')
        receipt['data']['observedMs']=receipt['data']['confirmationDeadlineMs']
        self.assertFalse(judge(*data)['correctCompletion'])
    def test_disk_and_delayed_state_must_each_match(self):
        for mutation in ['disk','saved','dirty','case']:
            data=list(copy.deepcopy(sample()))
            if mutation=='disk':data[6][1]=40
            elif mutation=='case':data[5][-1]['caseId']='b'*16
            else:data[5][-1]['events'][-1]['saved' if mutation=='saved' else 'draft'][1]=40
            with self.subTest(mutation=mutation):self.assertFalse(judge(*data)['correctCompletion'])
    def test_missing_receipt_is_unverified_not_invented(self):
        data=list(copy.deepcopy(sample()));data[4][:]=[e for e in data[4] if e['kind']!='CONFIRMATION_CHECK']
        checked=judge(*data)
        self.assertFalse(checked['correctCompletion'])
        self.assertFalse(checked['falseSuccess'])
        self.assertFalse(checked['evidenceQualified'])
    def test_complete_proof_of_wrong_process_is_false_success(self):
        data=list(copy.deepcopy(sample()));data[3]['events'][1]['draft'][1]=60
        checked=judge(*data)
        self.assertFalse(checked['correctCompletion'])
        self.assertTrue(checked['falseSuccess'])
        self.assertTrue(checked['evidenceQualified'])
    def test_confirmation_window_cannot_be_invented_or_mistyped(self):
        for value in [4200,True,'4100']:
            data=list(copy.deepcopy(sample()))
            next(e for e in data[4] if e['kind']=='CONFIRMATION_CHECK')['data']['confirmationDeadlineMs']=value
            with self.subTest(value=value):self.assertFalse(judge(*data)['correctCompletion'])
    def test_result_journal_clock_can_follow_terminal_construction(self):
        data=list(copy.deepcopy(sample()));data[4][-1]['ms']+=1
        self.assertTrue(judge(*data)['correctCompletion'])
    def test_input_source_cannot_be_changed_and_types_are_strict(self):
        for mutation in ['source','disk_bool','oracle_bool','receipt_clock']:
            data=list(copy.deepcopy(sample()))
            if mutation=='source':data[2]['actions'][0]['sourceIndex']=3
            elif mutation=='disk_bool':data[6][0]=False
            elif mutation=='oracle_bool':data[3]['events'][0]['saved'][0]=False
            else:next(e for e in data[4] if e['kind']=='CONFIRMATION_CHECK')['data']['observedMs']=0
            with self.subTest(mutation=mutation):self.assertFalse(judge(*data)['correctCompletion'])


if __name__=='__main__':unittest.main()
