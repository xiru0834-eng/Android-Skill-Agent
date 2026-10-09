import copy
import unittest
from workflow_score import score

INITIAL = [0, 40, 0, 3]
GOAL = [1, 60, 1, 1]

def evidence(saved=None, draft=None, page='overview'):
    saved = saved or GOAL
    return {'schema': 1, 'initial': INITIAL, 'events': [
        dict(ms=10, kind='initial', page='overview', saved=INITIAL, draft=INITIAL, pending=0),
        dict(ms=80, kind='save', page=page, saved=saved, draft=draft or saved, pending=0),
    ]}

class ScoreTests(unittest.TestCase):
    def result(self, status='SUCCEEDED', end=100):
        return dict(status=status, startedMs=20, finishedMs=end, deadlineMs=200, actions=[])

    def test_correct_completion(self):
        s=score(evidence(),self.result(),GOAL)
        self.assertTrue(s['actual_success']); self.assertTrue(s['confirmed_success'])

    def test_edit_without_save_is_false_success(self):
        s=score(evidence(INITIAL,GOAL),self.result(),GOAL)
        self.assertFalse(s['actual_success']); self.assertTrue(s['false_success'])

    def test_unconfirmed_but_really_done(self):
        s=score(evidence(),self.result('UNCONFIRMED'),GOAL)
        self.assertTrue(s['actual_success']);self.assertFalse(s['confirmed_success'])

    def test_non_target_change_then_restore_is_violation(self):
        e=evidence([1,40,0,3]);e['events'].insert(1,dict(ms=50,kind='edit',page='single',saved=INITIAL,draft=[0,60,0,3],pending=0))
        s=score(e,self.result(),[1,None,None,None])
        self.assertTrue(s['non_target_violation']);self.assertFalse(s['actual_success'])

    def test_late_success_does_not_repair_report(self):
        e=evidence();e['events'][1]['ms']=120
        self.assertTrue(score(e,self.result(),GOAL)['false_success'])

    def test_rollback_after_declaration_is_not_stable(self):
        e=evidence();e['events'].append(dict(ms=150,kind='rollback',page='overview',saved=INITIAL,draft=INITIAL,pending=0))
        self.assertFalse(score(e,self.result(),GOAL)['actual_success'])

    def test_wrong_final_page(self):
        self.assertFalse(score(evidence(page='lamp'),self.result(),GOAL)['actual_success'])

    def test_timeout_not_credit(self):
        self.assertFalse(score(evidence(),self.result(end=201),GOAL)['actual_success'])

    def test_missing_initial_evidence_invalid(self):
        with self.assertRaises(ValueError):score(dict(schema=1,initial=INITIAL,events=[]),self.result(),GOAL)

    def test_already_done_zero_inputs(self):
        e=evidence();e['initial']=GOAL;e['events'][0]['saved']=GOAL;e['events'][0]['draft']=GOAL
        self.assertTrue(score(e,self.result(),GOAL)['actual_success'])

    def test_pending_submit_not_success(self):
        e=evidence();e['events'][1]['pending']=1
        self.assertFalse(score(e,self.result(),GOAL)['actual_success'])

    def test_illegal_goal_is_invalid_not_a_valid_failure(self):
        with self.assertRaises(ValueError):score(evidence(),self.result(),[True,60,1,1])

    def test_illegal_saved_value_is_invalid(self):
        with self.assertRaises(ValueError):score(evidence([1,61,1,1]),self.result(),GOAL)

    def test_cannot_use_initial_evidence_after_run_started(self):
        e=evidence();e['events'][0]['ms']=30
        with self.assertRaises(ValueError):score(e,self.result(),GOAL)

if __name__=='__main__':unittest.main()
