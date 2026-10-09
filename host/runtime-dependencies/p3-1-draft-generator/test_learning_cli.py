import json
from pathlib import Path
import tempfile
import unittest
from learning_cli import main
from test_learning_request import PHONE, material


class CLITests(unittest.TestCase):
    def test_prepare_actual_material_does_not_call_model(self):
        with tempfile.TemporaryDirectory() as folder:
            code = main(['prepare', '--store', str(PHONE / 'phone-memory.sqlite'),
                         '--bundle', str(PHONE / 'PARAMETERROOM-bundle.json'), '--goal', '学习亮度调节', '--audit-root', folder])
            self.assertEqual(code, 0)
            records = list(Path(folder).glob('*/result.json'))
            out = json.loads(records[0].read_text())
            self.assertEqual(out['status'], 'MODEL_CONFIG_MISSING')
            self.assertEqual(out['calls'], 0)

    def test_generate_requires_current_config_budget_grant_not_old_authority(self):
        with tempfile.TemporaryDirectory() as folder:
            bad = Path(folder) / 'bad.json'
            bad.write_text('{}')
            code = main(['generate', '--request', str(bad), '--config', str(bad), '--grant', str(bad), '--budget', str(bad), '--audit-root', folder])
            self.assertEqual(code, 2)
            out = json.loads(list(Path(folder).glob('*/result.json'))[0].read_text())
            self.assertEqual(out['calls'], 0)
            self.assertEqual(out['status'], 'CLI_CONFIGURATION_ERROR')


if __name__ == '__main__': unittest.main()
