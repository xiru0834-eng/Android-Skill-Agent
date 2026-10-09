import copy
import unittest
from workflow_contract import compile_evidence, WorkflowError


def trace(actions, page='overview', initial=None):
    saved = list(initial or [0, 40, 0, 3]); draft = saved.copy(); steps = []
    def snap():
        values = {}
        for group in ('Lamp', 'Fan'):
            if page not in ('single', group.lower()): continue
            i = 0 if group == 'Lamp' else 2
            values['wf'+group+'Power'] = bool(draft[i])
            for value in ((20, 40, 60, 80, 100) if i == 0 else (1, 2, 3)):
                values['wf'+group+'Value'+str(value)] = draft[i+1] == value
        dirty = draft != saved if page in ('overview', 'single') else draft[(0 if page == 'lamp' else 2):(2 if page == 'lamp' else 4)] != saved[(0 if page == 'lamp' else 2):(2 if page == 'lamp' else 4)]
        return dict(page=page, values=values, saved=saved.copy() if page in ('overview', 'single') else [], dirty=dirty)
    initial = snap()
    for key in actions:
        before = snap(); group = 0 if 'Lamp' in key else 2
        if key == 'wfSingle': page = 'single'
        elif key == 'wfMulti': page = 'overview'
        elif key in ('wfOpenLamp', 'wfOpenFan'): page = key[6:].lower()
        elif key.endswith('Power'): draft[group] = 1-draft[group]
        elif 'Value' in key: draft[group+1] = int(key.split('Value')[1])
        elif key.endswith('Save'):
            saved[group:group+2] = draft[group:group+2]
            if page != 'single': page = 'overview'
        elif key.endswith('Cancel'):
            draft[group:group+2] = saved[group:group+2]
            if page != 'single': page = 'overview'
        elif key.endswith('Back'): page = 'overview'
        steps.append(dict(id=key, before=before, after=snap(), eventTime=len(steps)+1, attribution='RESOURCE_ID'))
    return dict(kind='WORKFLOW_TRACE', version=2, traceId='12345678-1234-1234-1234-123456789abc',
                appPackage='edu.sydney.transferlab', appVersion='3', source='AUTOMATED', goal='Demonstrated ordered process',
                end='STOPPED', error='', initial=initial, steps=steps, final=snap())


class FlexibleWorkflowTests(unittest.TestCase):
    def test_only_brightness_three_steps_preserves_power(self):
        s=compile_evidence(trace(['wfOpenLamp','wfLampValue60','wfLampSave']))
        self.assertEqual(s['version'],3)
        self.assertEqual(s['finalGoals'],[None,60,None,None])
    def test_single_page_power_only_two_steps(self):
        self.assertEqual(compile_evidence(trace(['wfLampPower','wfLampSave'],'single'))['finalGoals'],[1,None,None,None])
    def test_variable_lengths_revisit_and_intermediate_goals(self):
        for visits in range(1,12):
            actions=[]
            for i in range(visits): actions += ['wfOpenLamp','wfLampValue'+('60' if i%2==0 else '40'),'wfLampSave']
            s=compile_evidence(trace(actions))
            self.assertEqual(len(s['steps']),3*visits)
            self.assertEqual(s['steps'][2]['commitGoals'],[None,60,None,None])
    def test_reversed_order_and_mixed_controls(self):
        s=compile_evidence(trace(['wfOpenFan','wfFanValue1','wfFanPower','wfFanSave','wfOpenLamp','wfLampValue60','wfLampSave']))
        self.assertEqual(s['finalGoals'],[None,60,1,1])
    def test_power_on_then_off_not_collapsed(self):
        s=compile_evidence(trace(['wfLampPower','wfLampPower','wfLampSave'],'single'))
        self.assertEqual([x['desired'] for x in s['steps'][:2]],[True,False])
        self.assertEqual(s['finalGoals'],[0,None,None,None])
    def test_cancel_does_not_turn_unsaved_target_into_final_goal(self):
        s=compile_evidence(trace(['wfOpenLamp','wfLampPower','wfLampCancel','wfOpenFan','wfFanValue1','wfFanSave']))
        self.assertEqual(s['finalGoals'],[None,None,None,1])
    def test_single_page_independent_saves_and_layout_navigation(self):
        s=compile_evidence(trace(['wfSingle','wfLampPower','wfFanValue1','wfLampSave','wfFanSave','wfMulti']))
        self.assertEqual(s['finalGoals'],[1,None,None,1])
    def test_ambiguous_label_resolved_only_by_unique_full_transition(self):
        t=trace(['wfLampPower','wfFanValue1','wfLampSave','wfFanSave'],'single')
        for i,candidates in ((0,['wfLampPower','wfFanPower']),(2,['wfLampSave','wfFanSave']),(3,['wfLampSave','wfFanSave'])):
            t['steps'][i].update(attribution='UNIQUE_TRANSITION',candidateIds=candidates)
        self.assertEqual(compile_evidence(t)['finalGoals'],[1,None,None,1])
        for mode in ('duplicate','missing','foreign','wrong','extra'):
            bad=copy.deepcopy(t);step=bad['steps'][0]
            if mode=='duplicate':step['candidateIds']=['wfLampPower']*2
            elif mode=='missing':step.pop('candidateIds')
            elif mode=='foreign':step['candidateIds'].append('otherSwitch')
            elif mode=='wrong':step['candidateIds']=['wfFanPower','wfFanSave']
            else:step['after']['values']['wfFanPower']=True
            with self.subTest(mode=mode),self.assertRaises(WorkflowError):compile_evidence(bad)
    def test_identical_no_effect_candidates_are_not_guessed(self):
        t=trace(['wfLampPower','wfLampSave','wfLampSave'],'single')
        t['steps'][-1].update(attribution='UNIQUE_TRANSITION',candidateIds=['wfLampSave','wfFanSave'])
        with self.assertRaises(WorkflowError):compile_evidence(t)
    def test_explicit_already_selected_value_is_recorded(self):
        s=compile_evidence(trace(['wfOpenLamp','wfLampValue40','wfLampSave']))
        self.assertEqual(s['finalGoals'],[None,40,None,None])
    def test_return_after_restore_does_not_assume_one_demonstration_initial(self):
        s=compile_evidence(trace(['wfOpenLamp','wfLampPower','wfLampPower','wfLampBack','wfOpenFan','wfFanValue1','wfFanSave'],initial=[1,80,1,2]))
        self.assertEqual(s['finalGoals'],[None,None,None,1])
    def test_android_text_and_clock_types_are_not_looser_in_python(self):
        for goal,clock in [('😀'*121,1),('x',2**63),('x'*241,1)]:
            t=trace(['wfOpenLamp','wfLampValue60','wfLampSave']);t['goal']=goal;t['steps'][0]['eventTime']=clock
            with self.subTest(goal_length=len(goal),clock=clock),self.assertRaises(WorkflowError):compile_evidence(t)
    def test_bad_sequences_not_accepted_merely_because_length_is_free(self):
        for actions in (['wfLampPower'],['wfOpenLamp','wfLampPower'],['wfOpenLamp','wfFanPower','wfFanSave']):
            with self.subTest(actions=actions), self.assertRaises(WorkflowError):compile_evidence(trace(actions))
    def test_tail_and_discontinuous_and_fake_save_rejected(self):
        base=trace(['wfOpenLamp','wfLampValue60','wfLampSave'])
        for mutation in ('final','before','save','extra','type'):
            t=copy.deepcopy(base)
            if mutation=='final':t['final']['saved'][1]=80
            elif mutation=='before':t['steps'][1]['before']['values']['wfLampPower']=True
            elif mutation=='save':t['steps'][-1]['after']['saved'][0]=1;t['final']=t['steps'][-1]['after']
            elif mutation=='extra':t['steps'][1]['injected']='script'
            else:t['initial']['saved'][0]=False
            with self.subTest(mutation=mutation),self.assertRaises(WorkflowError):compile_evidence(t)


if __name__=='__main__':unittest.main()
