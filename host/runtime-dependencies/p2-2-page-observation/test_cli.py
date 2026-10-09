"""Actual local CLI subprocesses, never App/ADB/model E2E."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parent


def invoke(*args):
    return subprocess.run([sys.executable, str(BASE / 'observation_cli.py'), *map(str,args)], cwd=BASE,
                          capture_output=True, text=True, encoding='utf-8', timeout=10)


class CliTests(unittest.TestCase):
    def test_explicit_fixture_capture_reload_and_visible_search_in_separate_processes(self):
        with tempfile.TemporaryDirectory(prefix='p22-cli-') as tmp:
            db = Path(tmp) / 'memory.sqlite'; captured = invoke('fixture-capture', '--db', db, '--value', 80)
            self.assertEqual(captured.returncode, 0, captured.stderr)
            result = json.loads(captured.stdout); obs_id = result['saved']['observation_id']
            self.assertEqual(result['channel'], 'OFFLINE_CALLBACK_SIMULATION')
            self.assertEqual(result['model_calls'], 0); self.assertEqual(result['device_actions'], 0)
            inspected = invoke('inspect', '--db', db, '--id', obs_id)
            self.assertEqual(inspected.returncode, 0, inspected.stderr)
            self.assertEqual(json.loads(inspected.stdout)['observation']['tree']['nodes'][-1]['range']['value'], 80)
            found = invoke('search', '--db', db, '--id', obs_id, '--role', 'slider')
            self.assertEqual(json.loads(found.stdout)['candidate_count'], 1)
            self.assertFalse(json.loads(found.stdout)['is_live_ui_query'])

    def test_capture_android_reports_blocked_without_creating_database(self):
        with tempfile.TemporaryDirectory(prefix='p22-cli-') as tmp:
            db = Path(tmp) / 'memory.sqlite'; result = invoke('capture-android', '--db', db)
            self.assertEqual(result.returncode, 2); self.assertFalse(db.exists())
            self.assertEqual(json.loads(result.stdout)['code'], 'NATIVE_PIPELINE_NOT_WIRED')

    def test_missing_database_and_bad_inputs_are_explicit_and_do_not_echo_credentials(self):
        with tempfile.TemporaryDirectory(prefix='p22-cli-') as tmp:
            db = Path(tmp) / 'missing.sqlite'
            self.assertEqual(json.loads(invoke('inspect','--db',db,'--id','missing').stdout)['code'], 'MEMORY_NOT_FOUND')
            for args in [('fixture-capture','--db',db,'--value','101'), ('fixture-capture','--db',db,'--value','sk-proj-'+'Z'*30),
                         ('search','--db',db,'--id','missing','--limit','-1'), ('unsupported','sk-proj-'+'Z'*30)]:
                with self.subTest(command=args[0]):
                    result = invoke(*args); self.assertNotEqual(result.returncode,0)
                    self.assertNotIn('sk-proj-', result.stdout + result.stderr)
            self.assertFalse(db.exists())


if __name__ == '__main__': unittest.main()
