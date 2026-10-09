import json
from pathlib import Path
import tempfile
import unittest
from compiler import MODEL, ModelError
from paid_budget import PaidBudget
from semantic_parameter_calls import build_request
from test_semantic_parameter_calls import CATALOG


class PaidSemanticBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'ledger.json'
        self.request=build_request('Set desk lamp to 80 percent',CATALOG)

    def test_legacy_still_rejects_semantic_output_size(self):
        ledger=PaidBudget(self.path)
        with self.assertRaisesRegex(ModelError,'PAID_REQUEST_POLICY'):
            ledger.call(self.request,1,lambda *a,**k:self.fail('not authorised'))
        self.assertEqual(ledger.snapshot()['attempts'],0)

    def test_explicit_profile_reserves_before_send_and_settles(self):
        ledger=PaidBudget(self.path,request_profile='semantic-v2')
        def remote(body,timeout):
            saved=json.loads(self.path.read_text());self.assertEqual(saved['attempts'],1)
            self.assertEqual(saved['requestProfile'],'semantic-v2')
            self.assertEqual(saved['rows'][0]['outputBound'],4096)
            self.assertGreater(saved['exposureNanoUsd'],4096*11000)
            return dict(returned_model=MODEL,input_tokens=100,output_tokens=400)
        ledger.call(self.request,1,remote)
        self.assertEqual(ledger.snapshot()['rows'][0]['state'],'SETTLED')
        self.assertEqual(ledger.snapshot()['maxCalls'],200)

    def test_invalid_profiles_do_not_create_ledger(self):
        for name in ['unlimited','',None,{},True]:
            with self.subTest(name=name),self.assertRaisesRegex(ValueError,'REQUEST_PROFILE'):
                PaidBudget(self.path,request_profile=name)
            self.assertFalse(self.path.exists())

    def test_semantic_limits_tools_and_model_still_rejected(self):
        for i,override in enumerate([{'max_output_tokens':4097},{'max_output_tokens':True},{'tools':[{}]},
            {'input':[dict(role='user',content='x'*65537)]},{'model':'other'},{'service_tier':'priority'}]):
            ledger=PaidBudget(self.path.with_name(str(i)+'.json'),request_profile='semantic-v2')
            with self.assertRaisesRegex(ModelError,'PAID_REQUEST_POLICY'):
                ledger.call(dict(self.request,**override),1,lambda *a,**k:self.fail('must not send'))
            self.assertEqual(ledger.snapshot()['attempts'],0)

    def test_unknown_usage_keeps_reserve_and_exhausts_call_cap(self):
        ledger=PaidBudget(self.path,max_calls=1,request_profile='semantic-v2')
        ledger.call(self.request,1,lambda *a,**k:dict(returned_model=MODEL))
        self.assertEqual(ledger.snapshot()['rows'][0]['state'],'UNKNOWN_RESERVED')
        with self.assertRaisesRegex(ModelError,'PAID_CALL_CAP'):
            ledger.call(self.request,1,lambda *a,**k:self.fail('must not send'))

    def test_semantic_money_cap_and_exclusive_file_remain(self):
        ledger=PaidBudget(self.path,max_nano_usd=1,request_profile='semantic-v2')
        with self.assertRaisesRegex(ModelError,'PAID_MONEY_CAP'):
            ledger.call(self.request,1,lambda *a,**k:self.fail('must not send'))
        self.assertEqual(ledger.snapshot()['attempts'],0)
        with self.assertRaises(FileExistsError):PaidBudget(self.path,request_profile='semantic-v2')

    def test_over_output_usage_halts_semantic_profile(self):
        ledger=PaidBudget(self.path,request_profile='semantic-v2')
        with self.assertRaisesRegex(ModelError,'PAID_RESPONSE_POLICY'):
            ledger.call(self.request,1,lambda *a,**k:dict(returned_model=MODEL,input_tokens=100,output_tokens=4097))
        self.assertTrue(ledger.snapshot()['halted'])

    def test_large_semantic_request_has_explicit_byte_guard(self):
        request=dict(self.request,input=[dict(role='user',content='x'*40000)])
        ledger=PaidBudget(self.path,request_profile='semantic-v2')
        ledger.call(request,1,lambda *a,**k:dict(returned_model=MODEL))
        self.assertGreater(ledger.snapshot()['rows'][0]['inputBound'],40000)


if __name__=='__main__':unittest.main()
