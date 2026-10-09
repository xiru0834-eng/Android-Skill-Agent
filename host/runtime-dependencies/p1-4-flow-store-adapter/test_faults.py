from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from test_store import StoreTests
from p14deps import canonical, digest
from flow_store import FlowStore, StoreError

BASE = Path(__file__).resolve().parent


class FaultTests(StoreTests):
    def child(self, source):
        return subprocess.run([sys.executable, '-c', source, str(self.root)], cwd=BASE,
                              capture_output=True, text=True, encoding='utf-8', timeout=15)

    def test_F01_process_crash_mid_save_rolls_back_head_version_event(self):
        original = self.draft()
        self.store.close()
        source = '''
import os, sys
from flow_store import FlowStore
from p14deps import fixture_bundle, canonical
s=FlowStore.open(sys.argv[1]); f,p,t=fixture_bundle()
f['version']='1.0.1'; p['flow_refs'][0]['version']='1.0.1'
s.db.set_trace_callback(lambda sql: os._exit(71) if sql.startswith('INSERT INTO heads') else None)
s.save_draft(canonical(f),p,1)
'''
        result = self.child(source)
        self.assertEqual(result.returncode, 71)
        self.store = FlowStore.open(self.root)
        rows = self.store.list_versions()
        self.assertEqual([row['key'] for row in rows], [original['key']])
        self.assertEqual(self.store.db.execute('SELECT revision FROM heads').fetchone()[0], 1)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0], 1)

    def test_F02_process_crash_before_event_commit_keeps_DRAFT(self):
        row = self.draft()
        self.store.close()
        source = '''
import os, sys
from flow_store import FlowStore
from p14deps import fixture_bundle
s=FlowStore.open(sys.argv[1]); f,p,t=fixture_bundle()
s.db.set_trace_callback(lambda sql: os._exit(72) if sql=='COMMIT' else None)
s.check(f['id']+'@'+f['version'],1,t,None)
'''
        self.assertEqual(self.child(source).returncode, 72)
        self.store = FlowStore.open(self.root)
        loaded = self.store.load(row['key'])
        self.assertEqual((loaded['state'], loaded['revision']), ('DRAFT', 1))

    def test_F03_two_processes_revision_CAS_one_winner(self):
        row = self.draft()
        worker = '''
import json,sys
from flow_store import FlowStore,StoreError
s=FlowStore.open(sys.argv[1]); print('READY',flush=True); sys.stdin.readline()
try:
 r=s.invalidate(sys.argv[2],1,'INVALIDATED','operator.parallel')
 print(json.dumps({'result':'OK','revision':r['revision']}),flush=True)
except StoreError as e: print(json.dumps({'result':e.code}),flush=True)
finally: s.close()
'''
        workers = [subprocess.Popen([sys.executable, '-c', worker, str(self.root), row['key']], cwd=BASE,
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding='utf-8') for _ in range(2)]
        try:
            for process in workers:
                self.assertEqual(process.stdout.readline().strip(), 'READY')
            for process in workers:
                process.stdin.write('GO\n')
                process.stdin.flush()
            results = []
            for process in workers:
                output, error = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, error)
                results.append(json.loads(output)['result'])
            self.assertCountEqual(results, ['OK', 'REVISION_CONFLICT'])
            self.assertEqual(self.store.load(row['key'])['revision'], 2)
        finally:
            for process in workers:
                if process.poll() is None:
                    process.kill()
                process.communicate()

    def test_F04_storage_full_rolls_back_no_silent_overwrite(self):
        row = self.draft()
        current_pages = self.store.db.execute('PRAGMA page_count').fetchone()[0]
        self.store.db.execute('PRAGMA max_page_count=' + str(current_pages))
        self.flow['version'] = '1.0.1'
        self.package['flow_refs'][0]['version'] = '1.0.1'
        with self.assertRaises(StoreError) as caught:
            self.store.save_draft(' ' * 30000 + canonical(self.flow), self.package, 1)
        self.assertEqual(caught.exception.code, 'STORE_STORAGE_ERROR')
        self.assertEqual([r['key'] for r in self.store.list_versions()], [row['key']])
        self.assertEqual(self.store.db.execute('SELECT revision FROM heads').fetchone()[0], 1)

    def test_F05_busy_store_explicit_no_partial_history(self):
        row = self.draft()
        with closing(sqlite3.connect(self.root / FlowStore.FILENAME)) as other:
            other.execute('BEGIN IMMEDIATE')
            try:
                self.rejection('STORE_BUSY', lambda: self.store.invalidate(row['key'], 1, 'REVOKED', 'operator.cancel'))
            finally:
                other.rollback()
        self.assertEqual(self.store.load(row['key'])['revision'], 1)

    def test_F06_wrong_event_digest_detected(self):
        row = self.draft()
        with closing(sqlite3.connect(self.root / FlowStore.FILENAME)) as db, db:
            db.execute("UPDATE events SET sha256=?", ('0' * 64,))
        self.rejection('STORE_DIGEST_ERROR', lambda: self.store.load(row['key']))

    def test_F07_broken_event_chain_even_with_recomputed_digest(self):
        row = self.draft()
        self.store.check(row['key'], 1, self.task, None)
        with closing(sqlite3.connect(self.root / FlowStore.FILENAME)) as db, db:
            body = json.loads(db.execute('SELECT body_json FROM events WHERE revision=2').fetchone()[0])
            body['previous_hash'] = 'wrong_previous'
            db.execute('UPDATE events SET body_json=?,sha256=? WHERE revision=2', (canonical(body), digest(body)))
        self.rejection('STORE_EVENT_ERROR', lambda: self.store.load(row['key']))

    def test_F08_missing_event_no_stale_state_fallback(self):
        row = self.draft()
        with closing(sqlite3.connect(self.root / FlowStore.FILENAME)) as db, db:
            db.execute('DELETE FROM events WHERE key=?', (row['key'],))
        self.rejection('STORE_EVENT_ERROR', lambda: self.store.load(row['key']))

    def test_F09_invalid_database_is_preserved_not_recreated(self):
        other = self.root / 'corrupt'
        other.mkdir()
        path = other / FlowStore.FILENAME
        path.write_bytes(b'NOT_A_SQLITE_DB_TEST_FIXTURE')
        before = path.read_bytes()
        self.rejection('STORE_CORRUPT', lambda: FlowStore.open(other))
        self.assertEqual(path.read_bytes(), before)

    def test_F10_invalid_key_and_revision_type_are_not_sql(self):
        row = self.draft()
        for key in (None, '../outside', "' OR 1=1 --"):
            with self.subTest(key=key):
                with self.assertRaises(StoreError):
                    self.store.load(key)
        self.rejection('REVISION_TYPE_ERROR', lambda: self.store.invalidate(row['key'], True, 'REVOKED', 'operator.cancel'))
        self.assertEqual(self.store.load(row['key'])['state'], 'DRAFT')


def load_tests(loader, tests, pattern):
    return loader.suiteClass(FaultTests(name) for name in sorted(dir(FaultTests)) if name.startswith('test_F'))
