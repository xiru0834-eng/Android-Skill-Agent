import copy
import unittest
from transfer_protection import assess,late_effects


def sample(fault='dirty'):
    initial=[0,40,0,3]
    events=[dict(ms=0,kind='initial',saved=initial,draft=initial,page='overview',pending=0),
            dict(ms=1,kind='preset_dirty',saved=initial,draft=[0,60,0,3],page='overview',pending=0),
            dict(ms=6000,kind='audit_snapshot',saved=initial,draft=[0,60,0,3],page='overview',pending=0)]
    return dict(fault=fault),dict(startedMs=10,finishedMs=1000,status='UNCONFIRMED',reason='INVALID_START',actions=[]),dict(events=events),dict(evidence_complete=True,false_success=False),dict(actualInputsMatchRequested=True,lateAppInputs=0)


class ProtectionTests(unittest.TestCase):
    def test_late_navigation_is_not_hidden_by_no_more_inputs(self):
        _,_,o,_,_=sample();o['events'][-1]['page']='lamp'
        self.assertEqual(len(late_effects(o,1000)),1)
    def test_unchanged_post_terminal_audit_is_not_effect(self):
        _,_,o,_,_=sample();self.assertEqual(late_effects(o,1000),[])
    def test_change_before_terminal_not_late(self):
        _,_,o,_,_=sample();self.assertEqual(late_effects(o,7000),[])
    def test_preserves_dirty(self):self.assertTrue(assess(*sample())['protection_pass'])
    def test_not_any_stop_counts(self):
        c,r,o,s,a=sample();r['reason']='WRONG_APP'
        self.assertFalse(assess(c,r,o,s,a)['protection_pass'])
    def test_transient_draft_edit_fails(self):
        c,r,o,s,a=sample();bad=copy.deepcopy(o['events'][-1]);bad.update(ms=500,draft=[0,80,0,3]);o['events'].insert(2,bad)
        self.assertFalse(assess(c,r,o,s,a)['protection_pass'])
    def test_missing_trigger_not_pass(self):
        c,r,o,s,a=sample();o['events']=[o['events'][0],o['events'][-1]]
        self.assertFalse(assess(c,r,o,s,a)['protection_pass'])
    def test_late_input_fails(self):
        c,r,o,s,a=sample();a['lateAppInputs']=1
        self.assertFalse(assess(c,r,o,s,a)['protection_pass'])
    def test_success_cannot_be_protection(self):
        c,r,o,s,a=sample();r['status']='SUCCEEDED'
        self.assertFalse(assess(c,r,o,s,a)['protection_pass'])
    def test_positive_delay_separate(self):
        c,r,o,s,a=sample('delay');r['status']='SUCCEEDED';s['confirmed_success']=True
        v=assess(c,r,o,s,a);self.assertIsNone(v['protection_pass']);self.assertFalse(v['positive_challenge_pass'])
    def test_unknown_not_certified(self):
        c,r,o,s,a=sample();s['evidence_complete']=False
        self.assertFalse(assess(c,r,o,s,a)['protection_pass'])
    def test_drop_stops_at_save(self):
        c,r,o,s,a=sample('drop');o['initial']=[0,40,0,3]
        o['events'][1]['kind']='dropped_save';r['reason']='STEP_UNCONFIRMED'
        r['actions']=[dict(id=x) for x in ('wfOpenLamp','wfLampPower','wfLampValue60','wfLampSave')]
        self.assertTrue(assess(c,r,o,s,a)['protection_pass'])
        r['actions'].append(dict(id='wfOpenFan'))
        self.assertFalse(assess(c,r,o,s,a)['protection_pass'])
    def test_duplicate_rejects_before_business_edit(self):
        c,r,o,s,a=sample('duplicate');r['reason']='AMBIGUOUS:wfLampPower';r['actions']=[dict(id='wfOpenLamp')]
        v=assess(c,r,o,s,a);self.assertTrue(v['protection_pass'])
        self.assertEqual(v['trigger_basis'],'controller_error_and_frozen_fixture')
        r['actions'].append(dict(id='wfLampPower'))
        self.assertFalse(assess(c,r,o,s,a)['protection_pass'])
    def test_missing_reason_is_specific(self):
        c,r,o,s,a=sample('missing');r['reason']='MISSING:wfFanSave'
        from transfer_protection import ROUTE
        r['actions']=[dict(id=x) for x in ROUTE[:7]]
        self.assertTrue(assess(c,r,o,s,a)['protection_pass'])
        r['reason']='MISSING:wfOpenLamp'
        self.assertFalse(assess(c,r,o,s,a)['protection_pass'])
    def test_rollback_requires_two_commits(self):
        c,r,o,s,a=sample('rollback');r['reason']='FINAL_TARGET_MISMATCH'
        from transfer_protection import ROUTE
        r['actions']=[dict(id=x) for x in ROUTE]
        self.assertFalse(assess(c,r,o,s,a)['protection_pass'])
        o['events'].extend([dict(kind='save',saved=[1,60,0,3]),dict(kind='save',saved=[0,40,1,1])])
        self.assertTrue(assess(c,r,o,s,a)['protection_pass'])


if __name__=='__main__':unittest.main()
