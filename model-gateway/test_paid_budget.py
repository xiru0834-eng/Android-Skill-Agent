import copy
from pathlib import Path
import tempfile
import threading
import unittest
from compiler import MODEL, ModelError
from paid_budget import PaidBudget


def body():
    return dict(model=MODEL, store=False, reasoning={'effort':'none'}, temperature=0,
                max_output_tokens=300, input=[{'role':'user','content':'test'}], text={})


class PaidBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'ledger.json'

    def test_attempt_persisted_before_transport_and_valid_usage_settled(self):
        ledger=PaidBudget(self.path)
        def remote(request,timeout):
            self.assertEqual(ledger.snapshot()['attempts'],1)
            self.assertEqual(request['service_tier'],'default')
            return {'returned_model':MODEL,'input_tokens':100,'output_tokens':20}
        original=body();before=copy.deepcopy(original)
        ledger.call(original,1,remote)
        self.assertEqual(original,before)
        self.assertEqual(ledger.snapshot()['rows'][0]['state'],'SETTLED')

    def test_timeout_keeps_reserve_and_request_count_no_retry(self):
        ledger=PaidBudget(self.path,max_calls=1)
        def remote(request,timeout):raise ModelError('NETWORK_OR_TIMEOUT')
        with self.assertRaises(ModelError):ledger.call(body(),1,remote)
        reserved=ledger.snapshot()['exposureNanoUsd']
        self.assertGreater(reserved,0)
        with self.assertRaisesRegex(ModelError,'PAID_CALL_CAP'):ledger.call(body(),1,remote)
        self.assertEqual(ledger.snapshot()['attempts'],1)

    def test_missing_invalid_and_boolean_usage_not_free(self):
        for usage in ({},{'input_tokens':True,'output_tokens':1},{'input_tokens':100,'output_tokens':-1}):
            ledger=PaidBudget(self.path.with_name('ledger-'+str(len(usage))+str(usage.get('input_tokens'))+'.json'))
            ledger.call(body(),1,lambda request,timeout:dict(returned_model=MODEL,**usage))
            self.assertEqual(ledger.snapshot()['rows'][0]['state'],'UNKNOWN_RESERVED')

    def test_money_cap_before_send_and_exclusive_no_reset(self):
        ledger=PaidBudget(self.path,max_nano_usd=1)
        with self.assertRaisesRegex(ModelError,'PAID_MONEY_CAP'):
            ledger.call(body(),1,lambda *a,**k:self.fail('must not send'))
        self.assertEqual(ledger.snapshot()['attempts'],0)
        with self.assertRaises(FileExistsError):PaidBudget(self.path)

    def test_wrong_model_and_oversized_usage_halt(self):
        ledger=PaidBudget(self.path)
        with self.assertRaisesRegex(ModelError,'PAID_RESPONSE_POLICY'):
            ledger.call(body(),1,lambda *a,**k:dict(returned_model='other',input_tokens=1,output_tokens=1))
        with self.assertRaisesRegex(ModelError,'PAID_HALTED'):
            ledger.call(body(),1,lambda *a,**k:self.fail('must not send'))

    def test_tools_and_nontext_disallowed_before_attempt(self):
        for override in ({'tools':[{}]},{'model':'other'},{'max_output_tokens':301},
                         {'input':[{'role':'user','content':[{}]}]},{'service_tier':'priority'}):
            ledger=PaidBudget(self.path.with_name(str(len(list(Path(self.temp.name).iterdir())))+'.json'))
            with self.assertRaisesRegex(ModelError,'PAID_REQUEST_POLICY'):
                ledger.call(dict(body(),**override),1,lambda *a,**k:self.fail('must not send'))
            self.assertEqual(ledger.snapshot()['attempts'],0)

    def test_concurrent_reservations_obey_shared_cap(self):
        ledger=PaidBudget(self.path,max_calls=1);entered=threading.Event();release=threading.Event()
        def remote(*a,**k):entered.set();release.wait(2);return {'returned_model':MODEL}
        worker=threading.Thread(target=lambda:ledger.call(body(),1,remote));worker.start()
        try:
            self.assertTrue(entered.wait(1))
            with self.assertRaisesRegex(ModelError,'PAID_CALL_CAP'):ledger.call(body(),1,remote)
        finally:release.set();worker.join(2)
        self.assertEqual(ledger.snapshot()['attempts'],1)


if __name__=='__main__':unittest.main()
