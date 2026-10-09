"""Raw transfer audit rejects fabricated scores and missing records."""
import tempfile
import unittest
from pathlib import Path
from workflow_experiment import write
from task4_report import audit,score_case


class ReportTests(unittest.TestCase):
    def test_missing_directories_keep_all_slots(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);result=audit(root/'source',root/'target',root/'runs',root/'audit')
            self.assertEqual(result['groups']['chain']['NOT_RUN'],3)
            self.assertEqual(result['groups']['normal']['NOT_RUN'],216)
            self.assertEqual(result['overall'],'NOT_READY')
    def test_export_failure_blocks_chain_not_fake_run_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'source').mkdir();(root/'runs/D0-native-S3-i0-r0').mkdir(parents=True)
            write(root/'source/failure.json',dict(reason='System UI ANR'))
            write(root/'runs/D0-native-S3-i0-r0/score.json',dict(correctCompletion=True,evidenceQualified=True))
            result=audit(root/'source',root/'target',root/'runs',root/'audit')
            self.assertEqual(result['groups']['chain']['BLOCKED'],3)
            self.assertEqual(result['groups']['normal']['UNVERIFIED'],1)
            self.assertEqual(result['groups']['normal']['PASS'],0)
    def test_wrong_case_or_missing_skill_cannot_be_qualified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);write(root/'case.json',dict(id='foreign'))
            score=score_case(root,dict(id='D0-native-S3-i0-r0',flow='S3',group='normal'))
            self.assertEqual(score['status'],'UNVERIFIED');self.assertFalse(score['evidenceQualified'])
    def test_audit_does_not_overwrite_prior_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);out=root/'audit';out.mkdir()
            with self.assertRaises(FileExistsError):audit(root/'source',root/'target',root/'runs',out)


if __name__=='__main__':unittest.main()
