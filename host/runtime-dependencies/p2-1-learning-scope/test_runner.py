import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BASE = Path(__file__).resolve().parent


class RunnerTests(unittest.TestCase):
    def test_frozen_inventory_has_unique_ids_and_pinned_existing_files(self):
        from run_checks import plan
        frozen = plan()
        self.assertEqual(len(frozen['cases']), len(set(frozen['cases'])))
        self.assertTrue(all(Path(file['path']).is_file() for file in frozen['files']))
        self.assertEqual(frozen['paid_requests'], 0)
        self.assertEqual(frozen['device_actions'], 0)

    def test_changed_candidate_is_blocked_before_running_cases(self):
        from run_checks import plan
        frozen = plan()
        frozen['files'][0]['sha256'] = '0' * 64
        with tempfile.TemporaryDirectory(prefix='p21-freeze-') as temporary:
            path = Path(temporary) / 'freeze.json'
            path.write_text(json.dumps(frozen), encoding='utf-8')
            result = subprocess.run([sys.executable, str(BASE / 'run_checks.py'), '--freeze', str(path)],
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['code'], 'FROZEN_FILE_CHANGED')
            self.assertEqual(result.stderr, '')
