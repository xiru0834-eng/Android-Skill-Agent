import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from p14deps import fixture_bundle, canonical
from flow_store import FlowStore

BASE = Path(__file__).resolve().parent


class CLITests(unittest.TestCase):
    def command(self, *args):
        return subprocess.run([sys.executable, str(BASE / 'store_cli.py'), *map(str, args)], cwd=BASE,
                              capture_output=True, text=True, encoding='utf-8', timeout=15)

    def test_C01_demo_is_labeled_fixture_and_reloadable(self):
        with tempfile.TemporaryDirectory(prefix='p14-cli-') as root:
            result = self.command('demo', '--root', root)
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data['lifecycle'], ['DRAFT', 'CHECKED', 'VALIDATED_SCOPE', 'PUBLISHED'])
            self.assertEqual(data['evidence_channel'], 'LOGIC_SIMULATION')
            self.assertEqual(data['model_calls'], 0)
            self.assertEqual(data['device_actions'], 0)
            self.assertFalse(data['reloaded']['execution_authority'])
            self.assertFalse(data['reloaded']['resume_authority'])

    def test_C02_missing_store_explicit_and_not_created(self):
        with tempfile.TemporaryDirectory(prefix='p14-cli-') as root:
            result = self.command('inspect', '--root', Path(root) / 'missing', '--key', 'flow.missing@1.0.0')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['code'], 'STORE_NOT_FOUND')
            self.assertFalse((Path(root) / 'missing').exists())

    def test_C03_export_has_no_publication_task_or_permissions(self):
        with tempfile.TemporaryDirectory(prefix='p14-cli-') as root:
            self.assertEqual(self.command('demo', '--root', root).returncode, 0)
            exported = self.command('export', '--root', root, '--key', 'flow.set_brightness@1.0.0')
            self.assertEqual(exported.returncode, 0)
            data = json.loads(exported.stdout)
            self.assertEqual(set(data), {'format', 'flow_raw', 'package', 'sha256'})
            self.assertNotIn('authorization_ref', exported.stdout)
            self.assertNotIn('PUBLISHED', exported.stdout)

    def test_C04_existing_store_not_deleted_or_reinitialized(self):
        with tempfile.TemporaryDirectory(prefix='p14-cli-') as root:
            self.assertEqual(self.command('demo', '--root', root).returncode, 0)
            before = (Path(root) / FlowStore.FILENAME).read_bytes()
            result = self.command('init', '--root', root)
            self.assertEqual(json.loads(result.stdout)['code'], 'STORE_ALREADY_EXISTS')
            self.assertEqual((Path(root) / FlowStore.FILENAME).read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
