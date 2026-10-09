"""Saved Android materials, no live observation or new device/model actions."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from p34deps import ROOT, canonical, digest
from material_package import archive_material, read_archive
from knowledge import KnowledgeError

BASE = Path(__file__).resolve().parent
CATALOG = ROOT / 'p3-1-draft-generator/evidence/frozen-confirmation-r1/material-results.json'


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p34-archive-'); self.root = Path(self.temp.name)
        self.row = [r for r in json.loads(CATALOG.read_text(encoding='utf-8')) if r['repetition'] == 1][0]

    def tearDown(self): self.temp.cleanup()

    def archive(self):
        return archive_material(self.row['audit_directory'], [self.row['historical_source']], self.root,
                                approved_roots=[ROOT])

    def test_M01_actual_missing_candidate_not_filled_with_fixture(self):
        directory = self.archive(); out = read_archive(directory, approved_roots=[ROOT])
        self.assertEqual(out['status'], 'BLOCKED_NO_CANDIDATE')
        self.assertIsNone(out['model_original']); self.assertIsNone(out['flow'])
        self.assertEqual(out['actual_points'], []); self.assertFalse(out['formal_retrievable'])
        self.assertGreater(len(out['learning_bundles'][0]['pages']), 0)
        self.assertEqual(out['model_cost']['calls'], 0)

    def test_M02_append_only_two_archives_not_overwrite(self):
        one, two = self.archive(), self.archive()
        self.assertNotEqual(one, two)
        self.assertEqual(read_archive(one, approved_roots=[ROOT]), read_archive(two, approved_roots=[ROOT]))

    def test_M03_damaged_archive_is_not_publication_evidence(self):
        directory = self.archive(); (directory / 'archive.json').write_text('{}', encoding='utf-8')
        with self.assertRaises(KnowledgeError): read_archive(directory, approved_roots=[ROOT])

    def test_M04_incomplete_archive_is_not_recreated(self):
        directory = self.archive(); (directory / 'complete.json').unlink()
        with self.assertRaises((KnowledgeError, OSError)): read_archive(directory, approved_roots=[ROOT])
        self.assertTrue((directory / 'archive.json').exists())

    def test_M05_changed_completion_filename_cannot_read_other_path(self):
        directory = self.archive()
        complete = json.loads((directory / 'complete.json').read_text(encoding='utf-8'))
        complete['file'] = '../other.json'; (directory / 'complete.json').write_text(canonical(complete), encoding='utf-8')
        with self.assertRaises(KnowledgeError): read_archive(directory, approved_roots=[ROOT])

    def test_M06_unknown_human_cost_and_original_failure_preserved(self):
        out = read_archive(self.archive(), approved_roots=[ROOT])
        self.assertIsNone(out['human_cost']['actions']); self.assertIsNone(out['human_cost']['minutes'])
        self.assertEqual(out['original_model_status'], 'MODEL_CONFIG_MISSING')
        self.assertFalse(out['current_ui_confirmed']); self.assertIn('REAL_CANDIDATE_MISSING', out['blocking_items'])

    def test_M07_unapproved_source_root_blocks_read(self):
        with self.assertRaises(KnowledgeError): read_archive(self.archive(), approved_roots=[self.root])

    def test_M08_new_process_reads_same_inert_material(self):
        directory = self.archive(); out = read_archive(directory, approved_roots=[ROOT])
        run = subprocess.run([sys.executable, '-X', 'utf8', str(BASE / 'cli.py'), '--read-archive', str(directory),
                              '--source-root', str(ROOT)], cwd=BASE, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads(run.stdout)
        self.assertEqual(result['readback'], 'PASS'); self.assertEqual(result['archive_digest'], digest(out))
        self.assertEqual(result['status'], 'BLOCKED_NO_CANDIDATE'); self.assertFalse(result['execution_authority'])


if __name__ == '__main__': unittest.main()
