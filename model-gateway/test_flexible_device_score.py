import copy
import unittest
from flexible_device_checks import score
from workflow_contract import compile_evidence
from test_flexible_workflow import trace

class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.initial=[0,40,0,3]
        self.skill=compile_evidence(trace(['wfOpenLamp','wfLampValue60','wfLampSave']))
        self.result=dict(status='SUCCEEDED',reason='VERIFIED',actions=[dict(id=s['id']) for s in self.skill['steps']],
                         completedSteps=3,finishedMs=50,startedMs=1,terminalStepIndex=3)
        self.events=[dict(ms=0,kind='initial',page='overview',saved=self.initial.copy(),draft=self.initial.copy(),pending=0)]
        for i,step in enumerate(self.skill['steps'],1):
            value=[0,60,0,3] if i>1 else self.initial.copy()
            self.events.append(dict(ms=i,kind=('edit:' if i==2 else 'input:')+step['id'],page=step['afterPage'],
                                    saved=value if i==3 else self.initial.copy(),draft=value,pending=0))
        self.oracle=dict(events=self.events)
        self.journal=[dict(kind='STEP_CONFIRMED',ms=i+.1,data=dict(sourceIndex=i)) for i in range(1,4)]
    def check(self):return score(self.skill,self.initial,self.result,self.oracle,self.journal)
    def test_independent_evidence_confirms_process_and_untouched_fields(self):
        self.assertTrue(self.check()['correctCompletion'])
    def test_final_only_cannot_substitute_for_order(self):
        self.journal=self.journal[-1:]
        self.assertTrue(self.check()['falseSuccess'])
    def test_intermediate_wrong_value_is_not_hidden_by_later_final_success(self):
        self.events[2]['draft']=[0,80,0,3]
        self.assertTrue(self.check()['falseSuccess'])
    def test_temporary_untouched_field_change_cannot_be_hidden_by_restore(self):
        self.events[1]['draft']=[1,40,0,3]
        self.assertTrue(self.check()['falseSuccess'])
    def test_premature_commit_is_not_hidden_by_correct_final_save(self):
        self.events[2]['saved']=[0,60,0,3]
        self.assertTrue(self.check()['falseSuccess'])
    def test_wrong_field_change_is_not_success(self):
        self.events[-1]['saved']=[1,60,0,3];self.events[-1]['draft']=[1,60,0,3]
        self.assertTrue(self.check()['falseSuccess'])
    def test_conservative_stop_is_not_false_success(self):
        self.result['status']='UNCONFIRMED';self.journal=[]
        self.assertFalse(self.check()['falseSuccess']);self.assertFalse(self.check()['correctCompletion'])
    def test_extra_input_cannot_be_hidden(self):
        self.events.append(dict(ms=4,kind='edit:wfFanPower',page='overview',saved=[0,60,0,3],draft=[0,60,0,3],pending=0))
        self.assertTrue(self.check()['falseSuccess'])

if __name__=='__main__':unittest.main()
