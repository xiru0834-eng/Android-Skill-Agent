import copy
import json
from pathlib import Path
import tempfile
import unittest
from compiler import MODEL
from accuracy_v2 import measure,cases_for
from accuracy_v2_export import replay,EvidenceError
from test_accuracy_v2 import BASE
from workflow_experiment import write


class ExportV2Tests(unittest.TestCase):
    def row(self,root,bad=False):
        case=next(c for c in cases_for(BASE) if c['caseId']=='preserve-fan-en')
        folder=root/'trials/000-G';folder.mkdir(parents=True)
        def transport(body,timeout):return dict(returned_model=MODEL,draft=dict(
            status='invoke',skill_id='9'*64 if bad else '3'*64,message='review'))
        return measure('G',case,folder,transport=transport)

    def test_valid_response_replays_without_any_remote(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);row=self.row(root);replay(root,0,row)
            self.assertTrue(row['correct'])

    def test_tampered_request_cannot_be_disguised_as_recorded_format_error(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);row=self.row(root,bad=True);self.assertFalse(row['available'])
            p=root/'trials/000-G/request-1.json';data=json.loads(p.read_text(encoding='utf-8'));data['model']='changed';write(p,data)
            with self.assertRaisesRegex(EvidenceError,'REQUEST_CHANGED'):replay(root,0,row)

    def test_missing_accepted_response_is_invalid(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);row=self.row(root)
            # A separate fake root avoids deleting an actual experiment artifact.
            alternate=root/'alternate';(alternate/'trials/000-G').mkdir(parents=True)
            p=root/'trials/000-G/request-1.json';write(alternate/'trials/000-G/request-1.json',json.loads(p.read_text(encoding='utf-8')))
            with self.assertRaisesRegex(EvidenceError,'MISSING_RESPONSE'):replay(alternate,0,row)

    def test_recorded_invalid_skill_is_failure_not_invalid_audit(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);row=self.row(root,bad=True);replay(root,0,row)
            self.assertFalse(row['correct']);self.assertEqual(row['failureClass'],'availability')


if __name__=='__main__':unittest.main()
