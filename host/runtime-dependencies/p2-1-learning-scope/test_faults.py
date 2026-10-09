from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

from learning_budget import LearningBudget
from learning_ledger import LearningLedger
from learning_scope import ScopeError, validate_scope
from test_ledger import cost_event
from test_scope import scope_fixture


class FaultTests(unittest.TestCase):
    def test_real_two_process_compare_and_swap_preserves_one_winner(self):
        with tempfile.TemporaryDirectory(prefix='p21-process-') as temporary:
            path = Path(temporary) / 'store.sqlite3'
            store = LearningLedger.create(path, scope_fixture())
            script = ("import json,sys; from learning_ledger import LearningLedger; from learning_scope import ScopeError; "
                      "s=LearningLedger.open(sys.argv[1]); e=json.loads(sys.argv[2]);\n"
                      "try: s.append(e,expected_revision=0); print('APPENDED')\n"
                      "except ScopeError as x: print(x.code)")
            processes = [subprocess.Popen([sys.executable, '-c', script, str(path), json.dumps(cost_event('cost.' + name))],
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                         for name in ('a', 'b')]
            outputs = [process.communicate(timeout=10) for process in processes]
            self.assertEqual(sum(output[0].strip() == 'APPENDED' for output in outputs), 1)
            self.assertEqual(sum(output[0].strip() == 'STORE_CONFLICT' for output in outputs), 1)
            self.assertTrue(all(not output[1] for output in outputs))
            self.assertEqual(store.inspect()['revision'], 1)

    def test_lock_timeout_fails_bounded_without_changing_head(self):
        with tempfile.TemporaryDirectory(prefix='p21-lock-') as temporary:
            path = Path(temporary) / 'store.sqlite3'
            store = LearningLedger.create(path, scope_fixture())
            with closing(sqlite3.connect(path)) as lock:
                lock.execute('BEGIN IMMEDIATE')
                with self.assertRaises(ScopeError) as result:
                    store.append(cost_event(), expected_revision=0)
                self.assertEqual(result.exception.code, 'STORE_BUSY')
                lock.rollback()
            self.assertEqual(store.inspect()['revision'], 0)

    def test_storage_capacity_blocks_and_preserves_last_commit(self):
        scope = scope_fixture()
        scope['budgets']['max_storage_bytes'] = 32768
        with tempfile.TemporaryDirectory(prefix='p21-capacity-') as temporary:
            path = Path(temporary) / 'store.sqlite3'
            store = LearningLedger.create(path, scope)
            revision = 0
            try:
                for number in range(80):
                    event = cost_event('cost.' + str(number), evidence_refs=['x' * 1900])
                    store.append(event, expected_revision=revision)
                    revision += 1
            except ScopeError as error:
                self.assertEqual(error.code, 'STORAGE_BUDGET_EXCEEDED')
            else:
                self.fail('capacity was not enforced')
            self.assertGreater(revision, 0)
            self.assertEqual(store.inspect()['revision'], revision)
            self.assertLessEqual(path.stat().st_size, 32768)

    def test_invalid_file_bytes_remain_unchanged_when_open_fails(self):
        with tempfile.TemporaryDirectory(prefix='p21-corrupt-') as temporary:
            path = Path(temporary) / 'store.sqlite3'
            raw = b'test-not-a-database'
            path.write_bytes(raw)
            with self.assertRaises(ScopeError):
                LearningLedger.open(path)
            self.assertEqual(path.read_bytes(), raw)

    def test_incompatible_source_mode_channel_is_rejected(self):
        for mode, channel, actor in (('AUTO_UI', 'HISTORICAL_ANDROID_TRACE', 'HUMAN_DECLARED'),
                                     ('DOCUMENT_ASSISTED', 'CURRENT_UI', 'DOCUMENT_AUTHOR'),
                                     ('EXPERT_CORRECTED', 'DOCUMENT', 'AUTOMATED')):
            scope = scope_fixture()
            scope['modes'] = [mode]
            scope['sources'][0].update(mode=mode, channel=channel, actor=actor)
            with self.subTest(mode=mode), self.assertRaises(ScopeError):
                validate_scope(scope)

    def test_threaded_budget_cannot_double_spend(self):
        scope = scope_fixture()
        scope['budgets']['max_actions'] = 1
        budget = LearningBudget(scope, clock=lambda: 1000)

        def consume(_):
            try:
                budget.charge({'actions': 1})
                return True
            except ScopeError:
                return False

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(consume, (1, 2)))
        self.assertEqual(results.count(True), 1)
        self.assertEqual(budget.snapshot()['spent']['actions'], 1)


if __name__ == '__main__':
    unittest.main()
