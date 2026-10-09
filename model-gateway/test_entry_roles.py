"""Model placement and resource recovery; all transports are injected, no keys."""
import threading
import unittest
from unittest.mock import patch
from compiler import ModelError
from selection_deadline import SelectionBudget,select_bounded
from start_teaching_bridge import resolve_bounded_selector
from test_selection_accuracy import CATALOG,response


class EntryRoleTests(unittest.TestCase):
    def test_primary_gpt_denial_does_not_consult_jev(self):
        with patch('deadline_remote.gpt_remote',return_value=dict(draft=dict(status='reject',skill_id=None,message='No'))), \
             patch('deadline_remote.jev_remote',side_effect=AssertionError('Jev must not run')):
            budget=SelectionBudget(8,max_calls=1)
            result=resolve_bounded_selector('gpt-safe')('Do not run anything.',CATALOG,budget)
        self.assertEqual(result['status'],'reject')
        self.assertEqual([r['provider'] for r in budget.calls],['GPT'])

    def test_primary_gpt_failure_does_not_consult_jev_or_retry(self):
        for failure in ['HTTP_429','HTTP_503','NETWORK_OR_TIMEOUT','MALFORMED_RESPONSE']:
            with self.subTest(failure=failure), \
                 patch('deadline_remote.gpt_remote',side_effect=ModelError(failure)) as remote, \
                 patch('deadline_remote.jev_remote',side_effect=AssertionError('No fallback')):
                budget=SelectionBudget(8,max_calls=1)
                with self.assertRaisesRegex(ModelError,failure):
                    resolve_bounded_selector('gpt-safe')('Run saved LampOnly60 workflow.',CATALOG,budget)
                self.assertEqual(remote.call_count,1)
                self.assertEqual(len(budget.calls),1)

    def test_primary_unknown_identity_cannot_open_review_or_call_jev(self):
        draft=dict(draft=dict(status='invoke',skill_id='f'*64,message='Review'))
        with patch('deadline_remote.gpt_remote',return_value=draft) as remote, \
             patch('deadline_remote.jev_remote',side_effect=AssertionError('No fallback')):
            with self.assertRaises(ValueError):
                resolve_bounded_selector('gpt-safe')('Run saved LampOnly60 workflow.',CATALOG,SelectionBudget(8,max_calls=1))
        self.assertEqual(remote.call_count,1)

    def test_optional_local_route_remains_revocable_without_model(self):
        with patch('deadline_remote.jev_remote',side_effect=AssertionError('No network')):
            budget=SelectionBudget(8)
            got=resolve_bounded_selector('routed')('Run LampOnly60.',CATALOG,budget)
            self.assertEqual(got['skill_id'],'b'*64);self.assertEqual(budget.calls,[])
            with self.assertRaisesRegex(ModelError,'CANCELLED'):
                resolve_bounded_selector('routed')('Run LampOnly60.',CATALOG,SelectionBudget(8,cancelled=lambda:True))

    def test_hybrid_negative_decisions_do_not_escalate_to_gpt(self):
        for choice in ['reject','clarify']:
            with self.subTest(choice=choice):
                budget=SelectionBudget(8)
                result=select_bounded('H2','Explain the routines.',CATALOG,budget,
                    lambda body,timeout:response(choice=choice,confidence=.99,prob=.99),
                    lambda *a,**k:self.fail('negative decision escalated'))
                self.assertEqual(result['status'],choice)
                self.assertEqual([r['provider'] for r in budget.calls],['Jev'])

    def test_hybrid_second_call_cannot_reactivate_after_catalog_revocation(self):
        current=[True];budget=SelectionBudget(8,is_current=lambda:current[0])
        def gpt(body,timeout):
            current[0]=False
            return dict(draft=dict(status='invoke',skill_id='b'*64,message='Review'))
        with self.assertRaisesRegex(ModelError,'STALE_REQUEST'):
            select_bounded('H2','Only lamp ON at sixty percent, fan unchanged.',CATALOG,budget,
                lambda body,timeout:response(),gpt)
        self.assertEqual([r['provider'] for r in budget.calls],['Jev','GPT'])

    def test_two_cancelled_workers_hold_capacity_until_actual_exit_then_recover(self):
        pool=threading.BoundedSemaphore(2);release=threading.Event()
        entered=[threading.Event(),threading.Event()];cancel=[threading.Event(),threading.Event()]
        budgets=[SelectionBudget(1,pool=pool,cancelled=e.is_set) for e in cancel]
        errors=[];workers=[]
        def caller(i):
            def stuck(body,timeout):entered[i].set();release.wait(3);return 'too late'
            try:budgets[i].call(stuck,{},'injected')
            except ModelError as error:errors.append(str(error))
        try:
            for i in range(2):
                worker=threading.Thread(target=caller,args=(i,));worker.start();workers.append(worker)
                self.assertTrue(entered[i].wait(1));cancel[i].set();worker.join(1)
                self.assertFalse(worker.is_alive())
            self.assertEqual(errors,['SELECTION_CANCELLED','SELECTION_CANCELLED'])
            with self.assertRaisesRegex(ModelError,'REMOTE_BUSY'):
                SelectionBudget(1,pool=pool).call(lambda *a,**k:self.fail('over capacity'),{},'injected')
        finally:
            release.set()
            for worker in workers:worker.join(2)
        # Acquiring both slots is a deterministic completion barrier, not a sleep.
        for _ in range(2):self.assertTrue(pool.acquire(timeout=1))
        for _ in range(2):pool.release()
        self.assertEqual(SelectionBudget(1,pool=pool).call(lambda body,timeout:'fresh',{},'injected'),'fresh')
        self.assertEqual([b.calls[0]['outcome'] for b in budgets],['SELECTION_CANCELLED','SELECTION_CANCELLED'])

    def test_one_call_cap_does_not_reset_but_new_request_has_fresh_budget(self):
        pool=threading.BoundedSemaphore(1);budget=SelectionBudget(8,pool=pool,max_calls=1)
        self.assertEqual(budget.call(lambda body,timeout:'first',{},'GPT'),'first')
        with self.assertRaisesRegex(ModelError,'PER_REQUEST_CAP'):
            budget.call(lambda *a,**k:self.fail('second call'),{},'GPT')
        self.assertEqual(len(budget.calls),1)
        self.assertEqual(SelectionBudget(8,pool=pool,max_calls=1).call(lambda body,timeout:'new',{},'GPT'),'new')


if __name__=='__main__':unittest.main()
