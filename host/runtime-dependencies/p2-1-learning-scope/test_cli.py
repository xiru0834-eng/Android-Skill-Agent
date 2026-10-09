import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from test_ledger import cost_event
from test_scope import scope_fixture

BASE = Path(__file__).resolve().parent


class CliTests(unittest.TestCase):
    def invoke(self, *args):
        result = subprocess.run([sys.executable, str(BASE / 'scope_cli.py'), *map(str, args)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.stderr, '')
        return result.returncode, json.loads(result.stdout)

    def test_real_local_create_append_inspect_roundtrip(self):
        with tempfile.TemporaryDirectory(prefix='p21-cli-') as temporary:
            root = Path(temporary)
            scope_path, event_path, database = root / 'scope.json', root / 'event.json', root / 'store.sqlite3'
            scope_path.write_text(json.dumps(scope_fixture()), encoding='utf-8')
            event_path.write_text(json.dumps(cost_event()), encoding='utf-8')
            code, result = self.invoke('create', scope_path, database)
            self.assertEqual(code, 0)
            code, result = self.invoke('append', database, event_path, '--revision', 0)
            self.assertEqual(code, 0)
            code, result = self.invoke('inspect', database)
            self.assertEqual(result['human_cost']['DEMONSTRATION']['total'], 1)
            self.assertFalse(result['execution_authority'])

    def test_cli_assess_reports_blocked_without_phone_or_model(self):
        with tempfile.TemporaryDirectory(prefix='p21-cli-') as temporary:
            path = Path(temporary) / 'scope.json'
            path.write_text(json.dumps(scope_fixture()), encoding='utf-8')
            code, result = self.invoke('assess', path)
            self.assertEqual(code, 2)
            self.assertEqual(result['status'], 'BLOCKED')
            self.assertIn('GAP_ORIGINAL_FORMAL_GATE', result['gaps'])

    def test_cli_source_audit_is_real_file_channel_not_android_execution(self):
        code, result = self.invoke('audit-sources')
        self.assertEqual(code, 0)
        self.assertEqual(len(result['audits']), 2)
        self.assertEqual(result['device_actions'], 0)
        self.assertEqual(result['model_calls'], 0)

    def test_cli_invalid_and_credential_input_never_echoes_payload(self):
        with tempfile.TemporaryDirectory(prefix='p21-cli-') as temporary:
            path = Path(temporary) / 'scope.json'
            scope = scope_fixture()
            scope['task']['goal'] = 'sk-proj-' + 'test-do-not-echo'
            path.write_text(json.dumps(scope), encoding='utf-8')
            code, result = self.invoke('validate', path)
            self.assertEqual(code, 1)
            self.assertEqual(result['code'], 'SENSITIVE_INPUT')
            self.assertNotIn('test-do-not-echo', json.dumps(result))


if __name__ == '__main__':
    unittest.main()
