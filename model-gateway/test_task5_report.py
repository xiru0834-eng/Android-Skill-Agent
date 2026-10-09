import tempfile
import unittest
import io
import json
import sys
from contextlib import redirect_stderr
from unittest.mock import patch
from pathlib import Path
from recovery_evidence import seal, verify, files
import task5_report
from task5_report import verify_bundle


class BundleTests(unittest.TestCase):
    def test_changed_sealed_report_is_rejected_before_scoring(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'report.md').write_text('original');seal(root)
            (root/'report.md').write_text('changed')
            result=verify_bundle(root)
            self.assertFalse(result['valid']);self.assertEqual(result['phase'],'SEALED_BUNDLE_INTEGRITY')

    def invoke(self, root, target):
        with patch.object(task5_report,'ROOT',root), patch.object(sys,'argv',['task5_report','--output',str(target)]), redirect_stderr(io.StringIO()):
            try: task5_report.main()
            except (SystemExit,OSError,ValueError,RuntimeError): pass

    def test_existing_sealed_output_is_rejected_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'output/autonomous-five/task-5/old';target.mkdir(parents=True)
            (target/'report.md').write_text('original',encoding='utf-8');seal(target)
            self.invoke(root,target)
            self.assertTrue(verify(target)['valid'])

    def test_existing_failure_receipt_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'output/autonomous-five/task-5/old';target.mkdir(parents=True)
            (target/'failure.json').write_text('{"original":true}',encoding='utf-8');before=files(target)
            self.invoke(root,target)
            self.assertEqual(files(target),before)

    def test_concurrent_directory_creation_cannot_receive_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'output/autonomous-five/task-5/new'
            def competitor(out):
                out.mkdir(parents=True);(out/'owner.txt').write_text('competitor',encoding='utf-8');seal(out)
                raise FileExistsError('competitor created output')
            with patch.object(task5_report,'build',side_effect=competitor):self.invoke(root,target)
            self.assertTrue(verify(target)['valid'])

    def test_task5_root_itself_is_not_an_output_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'output/autonomous-five/task-5'
            self.invoke(root,target)
            self.assertFalse(target.exists())

    def test_new_owned_pipeline_failure_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'output/autonomous-five/task-5/new'
            with patch.object(task5_report,'verify',return_value={'valid':True}),patch.object(task5_report,'all_historical',side_effect=RuntimeError('test failure')):
                self.invoke(root,target)
            receipt=json.loads((target/'failure.json').read_text(encoding='utf-8'))
            self.assertEqual(receipt['phase'],'HOST_EVIDENCE_PIPELINE');self.assertEqual(receipt['error'],'RuntimeError')

    def test_replaced_output_directory_is_not_owned_anymore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'output/autonomous-five/task-5/new'
            def replace(_):
                target.rename(target.with_name('owned-original'));target.mkdir()
                (target/'owner.txt').write_text('replacement',encoding='utf-8');seal(target)
                raise RuntimeError('output replaced')
            with patch.object(task5_report,'verify',return_value={'valid':True}),patch.object(task5_report,'all_historical',side_effect=replace):
                self.invoke(root,target)
            self.assertTrue(verify(target)['valid'])

    def test_direct_build_rejects_existing_directory_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'old';target.mkdir()
            (target/'report.md').write_text('original',encoding='utf-8');seal(target)
            with self.assertRaises(FileExistsError):task5_report.build(target)
            self.assertTrue(verify(target)['valid'])

    def test_receipt_io_failure_does_not_replace_pipeline_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'new';original=RuntimeError('original failure')
            with patch.object(task5_report,'populate',side_effect=original),patch.object(Path,'open',side_effect=OSError('receipt storage failed')):
                with self.assertRaises(RuntimeError) as caught:task5_report.build(target)
            self.assertIs(caught.exception,original)

    def test_owned_existing_failure_receipt_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'new'
            def fail(out):
                (out/'failure.json').write_text('{"original":true}',encoding='utf-8')
                raise RuntimeError('next failure')
            with patch.object(task5_report,'populate',side_effect=fail):
                with self.assertRaises(RuntimeError):task5_report.build(target)
            self.assertEqual((target/'failure.json').read_text(encoding='utf-8'),'{"original":true}')

    def test_output_outside_task5_is_rejected_without_creating_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);target=root/'output/elsewhere/new'
            self.invoke(root,target)
            self.assertFalse(target.exists())
