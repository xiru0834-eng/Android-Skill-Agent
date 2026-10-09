import copy
import tempfile
import unittest
from pathlib import Path
from bundle_contract import BundleError
from bundle_store import BundleStore
from test_support import ENV,bundle_fixture
from learning_queries import LearningQueries

class QueryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'memory.sqlite'
        with BundleStore(self.path,create=True) as s:s.append(bundle_fixture(),expected_revision=0)
        self.store=BundleStore(self.path,read_only=True);self.q=LearningQueries(self.store)
    def tearDown(self):self.store.close();self.temp.cleanup()
    def test_list(self):
        r=self.q.list_pages(ENV);self.assertEqual(1,len(r['items']));self.assertFalse(r['execution_authority'])
    def test_inspect_page(self):self.assertEqual('page.a',self.q.inspect_page(ENV,'page.a')['page']['page_id'])
    def test_inspect_region(self):self.assertEqual(1,len(self.q.inspect_region(ENV,'page.a','region.page.a')['items']))
    def test_search(self):self.assertEqual(1,self.q.search_semantic_targets(ENV,role='slider')['candidate_count'])
    def test_unknown_page(self):self.assertEqual('NOT_FOUND',self.q.inspect_page(ENV,'missing')['status'])
    def test_unknown_region(self):self.assertEqual('NOT_FOUND',self.q.inspect_region(ENV,'page.a','missing')['status'])
    def test_unknown_env(self):self.assertEqual([],self.q.list_pages({**ENV,'ui_revision':'u1'})['items'])
    def test_missing_target(self):self.assertEqual('NOT_FOUND',self.q.search_semantic_targets(ENV,text='fan')['status'])
    def test_bad_limit(self):
        for limit in [-1,0,101,True,'1',None]:
            with self.subTest(limit=limit),self.assertRaises(BundleError):self.q.list_pages(ENV,limit=limit)
    def test_paths(self):
        for pid in ['../x','C:/Users/zz/a','/data/x']:
            with self.subTest(pid=pid),self.assertRaises(BundleError):self.q.inspect_page(ENV,pid)
    def test_bad_environment(self):
        with self.assertRaises(BundleError):self.q.list_pages('/data/x')
    def test_search_requires_filter(self):
        with self.assertRaises(BundleError):self.q.search_semantic_targets(ENV)
    def test_bad_text(self):
        for text in ['',1,'x'*257]:
            with self.subTest(text=str(text)[:8]),self.assertRaises(BundleError):self.q.search_semantic_targets(ENV,text=text)
    def test_no_live_current_or_authority(self):
        for r in [self.q.list_pages(ENV),self.q.inspect_page(ENV,'page.a'),self.q.inspect_region(ENV,'page.a','region.page.a'),self.q.search_semantic_targets(ENV,text='Brightness')]:
            self.assertFalse(r['current_ui_confirmed']);self.assertFalse(r['execution_authority']);self.assertEqual(0,r['implicit_observe_calls']);self.assertEqual(0,r['device_action_calls'])
    def test_region_fullpage_fallback(self):self.assertEqual(1,self.q.search_semantic_targets(ENV,text='Brightness',preferred_region_id='wrong')['candidate_count'])
    def test_no_disk_write(self):
        before=self.path.read_bytes();self.q.list_pages(ENV);self.q.inspect_page(ENV,'page.a');self.q.inspect_region(ENV,'page.a','region.page.a');self.q.search_semantic_targets(ENV,role='slider');self.assertEqual(before,self.path.read_bytes())
    def test_conflicting_cursor(self):
        with BundleStore(self.path) as s:s.append(bundle_fixture(page_id='page.b'),expected_revision=1)
        r=self.q.list_pages(ENV,limit=1);self.assertIsNotNone(r['next_cursor'])
        with self.assertRaises(BundleError):self.q.list_pages({**ENV,'ui_revision':'u1'},limit=1,cursor=r['next_cursor'])
    def test_pagination_no_duplication(self):
        with BundleStore(self.path) as s:s.append(bundle_fixture(page_id='page.b'),expected_revision=1)
        a=self.q.list_pages(ENV,limit=1);b=self.q.list_pages(ENV,limit=1,cursor=a['next_cursor']);self.assertNotEqual(a['items'][0]['page_id'],b['items'][0]['page_id']);self.assertIsNone(b['next_cursor'])
    def test_revision_cursor(self):
        with BundleStore(self.path) as s:s.append(bundle_fixture(page_id='page.b'),expected_revision=1)
        r=self.q.list_pages(ENV,limit=1)
        with BundleStore(self.path) as s:s.append(bundle_fixture(page_id='page.c'),expected_revision=2)
        with self.assertRaisesRegex(BundleError,'REVISION_CONFLICT'):self.q.list_pages(ENV,limit=1,cursor=r['next_cursor'])
    def test_tampered_cursor(self):
        for cursor in ['x','../x',{},'a'*2049]:
            with self.subTest(cursor=str(cursor)[:8]),self.assertRaises(BundleError):self.q.list_pages(ENV,cursor=cursor)
    def test_reloaded_latest(self):
        with BundleStore(self.path) as s:s.append(bundle_fixture(value=80),expected_revision=1)
        self.assertEqual(80,self.q.inspect_page(ENV,'page.a')['page']['dynamic_state'][0]['value'])
    def test_independent_context(self):
        import sys
        self.assertNotIn('android_bridge',sys.modules)
        self.assertNotIn('subprocess',__import__('learning_queries').__dict__)
    def test_memory_revision(self):self.assertEqual(1,self.q.list_pages(ENV)['memory_revision'])
    def test_readonly_constructor(self):
        with BundleStore(self.path) as s:
            with self.assertRaises(BundleError):LearningQueries(s)

if __name__=='__main__':unittest.main()
