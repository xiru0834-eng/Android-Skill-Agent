import tempfile,unittest,uuid,copy,json,threading
from pathlib import Path
from c2_inbox import DraftInbox
from c2_material import normalize_read_dependencies
BASE=Path('D:/Codex-deliveries/smarthome-ui-polish/p3-p5-product-wireup')
class InboxTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'inbox.sqlite';self.store=DraftInbox(self.path)
        self.id=uuid.uuid4().hex;self.flow=json.loads((BASE/'evidence/g2-reviewed-r2/flow.json').read_text(encoding='utf-8'))
    def tearDown(self):self.temp.cleanup()
    def fill(self):
        self.store.begin(self.id,{'goal':'调亮度','execution_authority':False})
        self.store.complete(self.id,{'candidate_flow':self.flow,'execution_authority':False})
    def test_only_draft_and_reload_name(self):
        self.fill();r=self.store.name(self.id,'我的灯');self.assertEqual('DRAFT',r['state'])
        self.assertFalse(r['execution_authority']);self.assertEqual('我的灯',DraftInbox(self.path).inspect(self.id)['name'])
    def test_repeat_generate_rejected(self):
        self.store.begin(self.id,{});
        with self.assertRaisesRegex(ValueError,'DUPLICATE_REQUEST'):self.store.begin(self.id,{})
    def test_cancel_late_callback_does_not_revive(self):
        self.store.begin(self.id,{});self.store.cancel(self.id)
        with self.assertRaisesRegex(ValueError,'CANCELLED_OR_STALE'):self.store.complete(self.id,{'candidate_flow':self.flow})
        self.assertEqual('CANCELLED',self.store.inspect(self.id)['state'])
    def test_empty_name(self):
        self.fill()
        for n in ('','  ',None,3,'x'*81):
            with self.assertRaises(ValueError):self.store.name(self.id,n)
    def test_name_is_not_path_or_identity(self):
        self.fill();r=self.store.name(self.id,'../测试');self.assertEqual(self.id,r['id']);self.assertEqual('DRAFT',r['state'])
    def test_model_self_publish_rejected(self):
        self.store.begin(self.id,{})
        with self.assertRaises(ValueError):self.store.complete(self.id,{'candidate_flow':self.flow,'execution_authority':True})
    def test_bad_id_never_reads_path(self):
        for bad in ('../a','C:/Windows',None,3):
            with self.assertRaises(ValueError):self.store.inspect(bad)
    def test_restart_running_is_not_permission_or_success(self):
        self.store.begin(self.id,{});r=DraftInbox(self.path).inspect(self.id)
        self.assertEqual('GENERATING',r['state']);self.assertFalse(r['execution_authority'])
    def test_concurrent_duplicate_admission(self):
        results=[]
        def run():
            try:self.store.begin(self.id,{});results.append('OK')
            except ValueError:results.append('NO')
        a=threading.Thread(target=run);b=threading.Thread(target=run);a.start();b.start();a.join();b.join()
        self.assertEqual(sorted(results),['NO','OK'])
    def test_model_budget_persists_and_never_refunds(self):
        for _ in range(4):self.store.reserve(1,limit=4)
        with self.assertRaisesRegex(ValueError,'MODEL_LIMIT'):DraftInbox(self.path).reserve(1,limit=4)
    def test_failure_is_not_draft(self):
        self.store.begin(self.id,{});self.store.fail(self.id,'MODEL_REFUSED')
        with self.assertRaises(ValueError):self.store.name(self.id,'fail')
    def test_incomplete_draft_rejected(self):
        self.store.begin(self.id,{})
        with self.assertRaises(ValueError):self.store.complete(self.id,{'candidate_flow':{'kind':'FlowSkill'}})
class IntegrityTests(unittest.TestCase):
    def test_corrupt_digest_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            inbox=DraftInbox(Path(d)/'inbox.sqlite');inbox.begin('a'*32,{})
            with inbox.connect() as db:db.execute("UPDATE drafts SET digest='bad'")
            with self.assertRaisesRegex(ValueError,'DRAFT_CORRUPT'):inbox.inspect('a'*32)
    def test_cancel_unknown_is_durable_tombstone(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'inbox.sqlite';DraftInbox(path).cancel('a'*32)
            other=DraftInbox(path);self.assertEqual(other.inspect('a'*32)['state'],'CANCELLED')
            with self.assertRaisesRegex(ValueError,'DUPLICATE_REQUEST'):other.begin('a'*32,{})

if __name__=='__main__':unittest.main(verbosity=2)
