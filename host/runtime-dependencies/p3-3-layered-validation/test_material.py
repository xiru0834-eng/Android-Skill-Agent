"""Original saved evidence and local files; no new model, phone or emulator input."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from p33deps import P32
from p33deps import canonical, digest
import hashlib
from material_io import inspect_material, save_report, read_saved

BASE = Path(__file__).resolve().parent
P31 = P32.parent / 'p3-1-draft-generator'


class MaterialTests(unittest.TestCase):
    def original(self):
        rows = json.loads((P31 / 'evidence/frozen-confirmation-r1/material-results.json').read_text(encoding='utf-8'))
        return next(r for r in rows if r['repetition'] == 1)

    def test_real_saved_material_has_no_candidate_and_cannot_be_substituted(self):
        row = self.original()
        out = inspect_material(row['audit_directory'], [row['historical_source']])
        self.assertEqual(out['status'], 'BLOCKED_NO_CANDIDATE')
        self.assertEqual(out['original_model_calls'], 0); self.assertTrue(out['source_unchanged'])
        self.assertTrue(all(v['status'] == 'NOT_TESTED' for v in out['layers'].values()))
        self.assertIsNone(out['compiled_plan'])

    def test_append_only_readback_preserves_ids_and_sources(self):
        row = self.original(); out = inspect_material(row['audit_directory'], [row['historical_source']])
        with tempfile.TemporaryDirectory(prefix='p33-audit-') as root:
            first = save_report(root, out); second = save_report(root, out)
            self.assertNotEqual(first, second); self.assertEqual(read_saved(first), out)
            self.assertEqual(read_saved(second), out)

    def test_tampered_report_and_incomplete_artifact_rejected(self):
        row = self.original(); out = inspect_material(row['audit_directory'], [row['historical_source']])
        with tempfile.TemporaryDirectory(prefix='p33-audit-') as root:
            directory = save_report(root, out)
            (directory / 'report.json').write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError): read_saved(directory)

    def test_incomplete_commit_and_path_traversal_artifact_rejected(self):
        row = self.original(); out = inspect_material(row['audit_directory'], [row['historical_source']])
        with tempfile.TemporaryDirectory(prefix='p33-audit-') as root:
            directory = save_report(root, out)
            complete = json.loads((directory / 'complete.json').read_text(encoding='utf-8'))
            complete['artifacts'][0]['file'] = '../report.json'
            (directory / 'complete.json').write_text(json.dumps(complete), encoding='utf-8')
            with self.assertRaises(ValueError): read_saved(directory)
            empty = Path(root) / 'incomplete'; empty.mkdir()
            with self.assertRaises(OSError): read_saved(empty)

    def test_missing_original_is_invalid_not_pass_or_new_candidate(self):
        with tempfile.TemporaryDirectory(prefix='p33-missing-') as root:
            out = inspect_material(root, [str(Path(root) / 'absent.json')])
            self.assertEqual(out['status'], 'AUDIT_INPUT_INVALID')
            self.assertIsNone(out['compiled_plan']); self.assertFalse(out['source_unchanged'])

    def test_matching_digest_does_not_make_malformed_report_valid(self):
        row = self.original(); out = inspect_material(row['audit_directory'], [row['historical_source']])
        with tempfile.TemporaryDirectory(prefix='p33-shape-') as root:
            directory = save_report(root, out)
            content = canonical([])
            (directory / 'report.json').write_text(content, encoding='utf-8')
            complete = json.loads((directory / 'complete.json').read_text(encoding='utf-8'))
            complete['report_digest'] = digest([])
            next(r for r in complete['artifacts'] if r['file'] == 'report.json')['sha256'] = hashlib.sha256(content.encode()).hexdigest()
            (directory / 'complete.json').write_text(canonical(complete), encoding='utf-8')
            with self.assertRaises(ValueError): read_saved(directory)

    def test_cli_fresh_process_and_no_implicit_execution_option(self):
        row = self.original(); out = inspect_material(row['audit_directory'], [row['historical_source']])
        with tempfile.TemporaryDirectory(prefix='p33-cli-') as root:
            directory = save_report(root, out)
            result = subprocess.run([sys.executable, '-X', 'utf8', str(BASE / 'cli.py'), '--read-saved', str(directory)],
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0); self.assertEqual(json.loads(result.stdout)['readback'], 'PASS')
            result = subprocess.run([sys.executable, '-X', 'utf8', str(BASE / 'cli.py'), '--execute'],
                                    capture_output=True, text=True, timeout=20)
            self.assertNotEqual(result.returncode, 0)


if __name__ == '__main__': unittest.main()
