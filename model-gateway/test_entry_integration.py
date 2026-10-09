import unittest
from unittest.mock import patch
from start_teaching_bridge import resolve_bounded_selector
from selection_deadline import SelectionBudget
from compiler import ModelError
from test_skill_selection import CATALOG
from test_jev_selection import response
from selection_routing import select_routed
from accuracy_confirmation import adjudicate

class EntryIntegrationTests(unittest.TestCase):
    def test_product_gpt_uses_one_deadline_aware_transport(self):
        calls=[]
        def fake(body,timeout):calls.append(timeout);return dict(draft=dict(status='invoke',skill_id='a'*64,message='Review'))
        with patch('deadline_remote.gpt_remote',fake):
            selected=resolve_bounded_selector('gpt')('Run 阅读60.',CATALOG,SelectionBudget(8,max_calls=1))
        self.assertEqual(selected['skill_id'],'a'*64);self.assertEqual(len(calls),1);self.assertLessEqual(calls[0],8)
    def test_safe_gpt_alias_is_same_primary_with_no_local_name_bypass(self):
        calls=[]
        def fake(body,timeout):calls.append(body);return dict(draft=dict(status='invoke',skill_id='a'*64,message='Review'))
        with patch('deadline_remote.gpt_remote',fake):
            self.assertEqual(resolve_bounded_selector('gpt-safe')('执行阅读60',CATALOG,SelectionBudget(8))['skill_id'],'a'*64)
        self.assertEqual(len(calls),1)
    def test_old_optional_route_gets_same_cancellation_and_deadline(self):
        with patch('deadline_remote.jev_remote',lambda body,timeout:response('clarify')):
            got=resolve_bounded_selector('routed')('Explain what this skill does.',CATALOG,SelectionBudget(8))
        self.assertEqual(got['status'],'clarify')
        with self.assertRaisesRegex(ModelError,'CANCELLED'):
            resolve_bounded_selector('routed')('执行阅读60',CATALOG,SelectionBudget(8,cancelled=lambda:True))
    def test_natural_identity_evidence_does_not_become_model_free_route(self):
        calls=[]
        def reject(body):calls.append(body);return response('reject')
        got=select_routed('Use the existing workflow named 阅读60 now.',CATALOG,reject)
        self.assertEqual(got['status'],'reject');self.assertEqual(len(calls),1)
    def test_scoring_rejects_wrong_identity_false_invoke_and_unavailable(self):
        for expected,selection,available in [(None,dict(status='invoke',skill_id='a'*64),True),
            ('a'*64,dict(status='invoke',skill_id='b'*64),True),
            ('a'*64,dict(status='invoke',skill_id='a'*64),False)]:
            row=adjudicate(dict(case=dict(expected=expected),selection=selection,available=available))
            self.assertFalse(row['correct'])
        self.assertEqual(adjudicate(dict(case=dict(expected=None),selection=dict(status='invoke',skill_id='a'*64),available=True))['failureClass'],'false_invoke')

if __name__=='__main__':unittest.main()
