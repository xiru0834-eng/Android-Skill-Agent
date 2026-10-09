import threading
import time
import unittest
from unittest.mock import patch
from compiler import ModelError
from selection_deadline import SelectionBudget, select_bounded
from test_selection_accuracy import CATALOG, response


def gpt_reply():
    return dict(draft=dict(status='invoke',skill_id='b'*64,message='Review only'))


class DeadlineTests(unittest.TestCase):
    def test_thread_start_failure_releases_capacity(self):
        pool=threading.BoundedSemaphore(1)
        with patch('selection_deadline.threading.Thread.start',side_effect=RuntimeError('cannot start')):
            with self.assertRaises(RuntimeError):SelectionBudget(1,pool=pool).call(lambda *a:None,{},'GPT')
        self.assertTrue(pool.acquire(False),'failed launch must not leak capacity')
        pool.release()
    def test_cancelled_at_entry_sends_nothing(self):
        budget=SelectionBudget(8,cancelled=lambda:True)
        with self.assertRaisesRegex(ModelError,'CANCELLED'):
            select_bounded('H2','Only lamp ON at sixty percent, fan unchanged.',CATALOG,budget,
                lambda *a:self.fail('remote'),lambda *a:self.fail('remote'))
        self.assertEqual(budget.calls,[])

    def test_deadline_at_entry_sends_nothing(self):
        now=[0.];budget=SelectionBudget(8,clock=lambda:now[0]);now[0]=8.
        with self.assertRaisesRegex(ModelError,'DEADLINE'):
            select_bounded('G','Use lamp routine.',CATALOG,budget)
        self.assertEqual(budget.calls,[])

    def test_second_call_only_gets_remaining_budget(self):
        now=[0.];budget=SelectionBudget(8,clock=lambda:now[0]);limits=[]
        def jev(body,timeout):limits.append(timeout);now[0]=3.;return response()
        def gpt(body,timeout):limits.append(timeout);now[0]=4.;return gpt_reply()
        got=select_bounded('H2','Only lamp ON at sixty percent, fan unchanged.',CATALOG,budget,jev,gpt)
        self.assertEqual(got['skill_id'],'b'*64);self.assertEqual(limits,[8.,5.])
        self.assertEqual([c['provider'] for c in budget.calls],['Jev','GPT'])

    def test_first_call_exhausts_budget_no_gpt(self):
        now=[0.];budget=SelectionBudget(8,clock=lambda:now[0])
        def jev(body,timeout):now[0]=8.;return response()
        with self.assertRaisesRegex(ModelError,'DEADLINE'):
            select_bounded('H2','Only lamp ON at sixty percent.',CATALOG,budget,jev,
                lambda *a:self.fail('GPT'))
        self.assertEqual(len(budget.calls),1)

    def test_cancel_after_jev_prevents_review(self):
        state=[False];budget=SelectionBudget(8,cancelled=lambda:state[0])
        def jev(body,timeout):state[0]=True;return response()
        with self.assertRaisesRegex(ModelError,'CANCELLED'):
            select_bounded('H2','Only lamp ON at sixty percent.',CATALOG,budget,jev,
                lambda *a:self.fail('GPT'))

    def test_changed_catalog_drops_high_confidence_result(self):
        current=[True];budget=SelectionBudget(8,is_current=lambda:current[0])
        def jev(body,timeout):current[0]=False;return response(confidence=.99,prob=.99)
        with self.assertRaisesRegex(ModelError,'STALE_REQUEST'):
            select_bounded('H2','Only lamp ON at sixty percent.',CATALOG,budget,jev)

    def test_cancel_after_gpt_drops_result(self):
        stop=[False];budget=SelectionBudget(8,cancelled=lambda:stop[0])
        def gpt(body,timeout):stop[0]=True;return gpt_reply()
        with self.assertRaisesRegex(ModelError,'CANCELLED'):
            select_bounded('H2','Only lamp ON at sixty percent.',CATALOG,budget,
                lambda body,timeout:response(),gpt)

    def test_blocking_worker_cannot_post_late_invoke(self):
        release=threading.Event();finished=threading.Event();budget=SelectionBudget(.12)
        def jev(body,timeout):release.wait(2);finished.set();return response()
        started=time.monotonic()
        try:
            with self.assertRaisesRegex(ModelError,'DEADLINE'):
                select_bounded('H2','Only lamp ON at sixty percent.',CATALOG,budget,jev,
                    lambda *a:self.fail('late GPT'))
            self.assertLess(time.monotonic()-started,.5)
            self.assertEqual(budget.calls[0]['outcome'],'SELECTION_DEADLINE')
        finally:release.set();self.assertTrue(finished.wait(1))

    def test_worker_capacity_is_not_unbounded(self):
        release=threading.Event();finished=threading.Event()
        pool=threading.BoundedSemaphore(1)
        def slow(body,timeout):release.wait(2);finished.set();return response()
        try:
            with self.assertRaisesRegex(ModelError,'DEADLINE'):
                SelectionBudget(.04,pool=pool).call(slow,{},'Jev')
            with self.assertRaisesRegex(ModelError,'REMOTE_BUSY'):
                SelectionBudget(1,pool=pool).call(slow,{},'Jev')
        finally:release.set();self.assertTrue(finished.wait(1))

    def test_explicit_denial_never_calls_gpt(self):
        budget=SelectionBudget(8)
        got=select_bounded('H2','Do not start anything.',CATALOG,budget,
            lambda body,timeout:response('reject',.99,.99),lambda *a:self.fail('GPT'))
        self.assertEqual(got['status'],'reject');self.assertEqual(len(budget.calls),1)

    def test_transport_failure_never_calls_gpt(self):
        def broken(body,timeout):raise ModelError('HTTP_503')
        budget=SelectionBudget(8)
        with self.assertRaisesRegex(ModelError,'HTTP_503'):
            select_bounded('H2','Only lamp ON.',CATALOG,budget,broken,lambda *a:self.fail('GPT'))
        self.assertEqual(budget.calls[0]['outcome'],'HTTP_503')


if __name__=='__main__':unittest.main()
