import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import repair_r3_confirm as confirm
from repair_r3_gate import sha


class ConfirmationTest(unittest.TestCase):
    def test_normal_evidence_parent_exists_before_evaluator(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)/'new-confirmation'
            def fake_case(*args):
                self.assertTrue((root/'normal').is_dir())
            with patch.object(confirm,'OUT',root),patch.object(confirm,'check_product'),patch.object(confirm.r3,'RUN'),patch.object(confirm.r3,'case_one',fake_case):
                confirm.normal('fake','E1',0)

    def test_native_product_change_is_rejected_before_device(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            (root/'candidate-v103').mkdir()
            (root/'native').mkdir()
            source=root/'native/Core.java'
            source.write_bytes(b'original')
            (root/'candidate-v103/freeze.json').write_text(json.dumps({'source_files':{'native\\Core.java':sha(b'original')}}))
            with patch.object(confirm,'ROOT',root),patch.object(confirm,'RUN',root),patch.object(confirm.r3,'APK',source),patch.object(confirm.r3,'APK_HASH',sha(b'original')):
                confirm.check_product()
                source.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'FROZEN_PRODUCT_CHANGED'):
                    confirm.check_product()

    def test_formal_commands_cannot_accept_diagnostic_timeout(self):
        rows=confirm.specs()
        self.assertEqual(len(rows),16)
        self.assertTrue(all(row['kind']=='device' and row['accept']==['PASS'] for row in rows))
        self.assertTrue(all(row['argv'] and row['source_files'] for row in rows))

    def test_g1_failed_row_is_saved_and_next_iteration_is_never_reached(self):
        import g1_device_eval as g1
        reached=[]
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            def fake_run(host,out):
                out.mkdir(parents=True)
                g1.save(out/'failed.json',{'case':'failed','assessment':{'passed':False}})
                reached.append('UNSAFE_NEXT_CASE')
            with patch.object(confirm,'OUT',root),patch.object(confirm,'check_product'),patch.object(g1,'run',fake_run),patch.object(g1,'prepare'),patch.object(g1,'assess'),patch.object(g1,'save'):
                with self.assertRaisesRegex(ValueError,'G1_CASE_FAILED'):
                    confirm.protection('fake','g1')
            self.assertEqual(reached,[])
            self.assertTrue((root/'regression/g1-fake/failed.json').exists())


if __name__=='__main__':
    unittest.main()
