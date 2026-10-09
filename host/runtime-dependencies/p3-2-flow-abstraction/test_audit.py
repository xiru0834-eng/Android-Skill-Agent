"""File/CLI receipts use synthetic protocol material unless explicitly marked historical."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from test_abstraction import fixtures
from p32deps import canonical
from audit_io import inspect_original, save_report


def audit_fixture(root, *, with_candidate=True):
    req, raw, bundles = fixtures(with_notes=True)
    directory = root / 'original'; directory.mkdir()
    (directory / 'input.json').write_text(canonical(req), encoding='utf-8')
    bpath = root / 'bundle.json'; bpath.write_text(canonical(bundles[0]), encoding='utf-8')
    result = {'status': 'MODEL_CONFIG_MISSING', 'calls': 0, 'execution_authority': False,
              'ready_for_device_execution': False, 'evidence_channel': 'NO_MODEL_CALL'}
    if with_candidate:
        draft = json.loads(raw)
        result.update(draft, status='DRAFT_WITH_KNOWLEDGE_GAPS', calls=1, evidence_channel='FAKE_MODEL_PROTOCOL_ONLY')
        (directory / '01-response.json').write_text(canonical({'raw_redacted': raw, 'raw_sha256': hashlib.sha256(raw.encode()).hexdigest(),
            'redaction_applied': False, 'finish_reason': 'stop', 'refusal': False}), encoding='utf-8')
    (directory / 'result.json').write_text(canonical(result), encoding='utf-8')
    return directory, bpath


class AuditTests(unittest.TestCase):
    def test_original_candidate_and_materials_are_kept_immutable(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); original, bundle = audit_fixture(root)
            before = {p: p.read_bytes() for p in original.iterdir()}
            before[bundle] = bundle.read_bytes()
            result = inspect_original(original, [bundle])
            self.assertEqual(result['status'], 'PARAMETERIZED_DRAFT')
            destination = save_report(root / 'new-audits', result)
            saved = json.loads((destination / 'report.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['revision_diff'], result['revision_diff'])
            self.assertTrue((destination / 'parameter-source-table.json').exists())
            self.assertTrue(all(p.read_bytes() == content for p, content in before.items()))
            self.assertFalse(saved['execution_authority'])

    def test_no_candidate_result_is_not_patched_with_example(self):
        with tempfile.TemporaryDirectory() as d:
            original, bundle = audit_fixture(Path(d), with_candidate=False)
            out = inspect_original(original, [bundle])
            self.assertEqual(out['status'], 'BLOCKED_NO_CANDIDATE')
            self.assertEqual(out['original_model_status'], 'MODEL_CONFIG_MISSING')
            self.assertIsNone(out['revised_flow'])

    def test_inconsistent_or_tampered_receipts_are_rejected(self):
        for change in ('zero_calls', 'raw_digest', 'result_flow', 'unknown_channel', 'redacted'):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as d:
                original, bundle = audit_fixture(Path(d))
                path = original / 'result.json'; result = json.loads(path.read_text())
                if change == 'zero_calls': result['calls'] = 0
                elif change == 'result_flow': result['candidate_flow']['purpose'] = 'altered'
                elif change == 'unknown_channel': result['evidence_channel'] = 'TRUST_ME'
                else:
                    rp = original / '01-response.json'; response = json.loads(rp.read_text())
                    response['raw_sha256' if change == 'raw_digest' else 'redaction_applied'] = '0' * 64 if change == 'raw_digest' else True
                    rp.write_text(canonical(response), encoding='utf-8')
                path.write_text(canonical(result), encoding='utf-8')
                self.assertEqual(inspect_original(original, [bundle])['status'], 'P31_RECEIPT_INCONSISTENT')

    def test_duplicate_json_keys_and_oversize_are_not_silently_loaded(self):
        with tempfile.TemporaryDirectory() as d:
            original, bundle = audit_fixture(Path(d), with_candidate=False)
            (original / 'result.json').write_text('{"calls":0,"calls":1}', encoding='utf-8')
            self.assertEqual(inspect_original(original, [bundle])['status'], 'AUDIT_INPUT_INVALID')
            (original / 'result.json').write_bytes(b' ' * (1048576 + 1))
            self.assertEqual(inspect_original(original, [bundle])['status'], 'AUDIT_INPUT_SIZE_LIMIT')

    def test_fresh_process_cli_readback_and_no_output_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); original, bundle = audit_fixture(root)
            cmd = [sys.executable, '-X', 'utf8', str(Path(__file__).parent / 'cli.py'),
                   '--p31-audit', str(original), '--bundle', str(bundle), '--output-root', str(root / 'audits')]
            for _ in range(2):
                run = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', timeout=20)
                self.assertEqual(run.returncode, 0, run.stderr)
                reply = json.loads(run.stdout)
                self.assertEqual(reply['status'], 'PARAMETERIZED_DRAFT')
            directories = list((root / 'audits').iterdir())
            self.assertEqual(len(directories), 2)
            self.assertNotEqual(directories[0].name, directories[1].name)

    def test_analysis_does_not_touch_network_processes_or_model_transport(self):
        with tempfile.TemporaryDirectory() as d:
            original, bundle = audit_fixture(Path(d))
            with patch('socket.socket', side_effect=AssertionError('NETWORK_FORBIDDEN')), \
                 patch('subprocess.Popen', side_effect=AssertionError('PROCESS_FORBIDDEN')):
                out = inspect_original(original, [bundle])
            self.assertEqual(out['status'], 'PARAMETERIZED_DRAFT')
            self.assertEqual(out['model_calls'], 0)
            self.assertEqual(out['device_actions'], 0)


if __name__ == '__main__': unittest.main()
