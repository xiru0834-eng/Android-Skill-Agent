import copy
import json
import tempfile
import unittest
from pathlib import Path

from evaluation_framework import summarize
from evaluation_import import audit_campaign, import_partial, score_proof

ROOT=Path(__file__).resolve().parents[1]/'evaluation/partial-workflow'


class EvaluationImportTests(unittest.TestCase):
    def test_real_raw_execution(self):
        folder=ROOT/'phone-matrix/run-000'
        files={p.stem:p for p in folder.glob('*.json')}
        expected=json.loads(files['case'].read_text(encoding='utf-8'))
        r=score_proof('partial',files,expected)
        self.assertTrue(r['checks']['task_confirmed'])

    def test_raw_tampering_rejected(self):
        folder=ROOT/'phone-matrix/run-000'
        with tempfile.TemporaryDirectory() as tmp:
            files={}
            for p in folder.glob('*.json'):
                d=json.loads(p.read_text(encoding='utf-8'))
                if p.stem=='oracle':d['initial'][0]=1-d['initial'][0]
                dest=Path(tmp)/p.name;dest.write_text(json.dumps(d));files[p.stem]=dest
            with self.assertRaises((ValueError,AssertionError)):
                score_proof('partial',files,json.loads(files['case'].read_text()))

    def test_expected_case_change_rejected(self):
        folder=ROOT/'phone-matrix/run-000';files={p.stem:p for p in folder.glob('*.json')}
        case=json.loads(files['case'].read_text());case['initial'][1]=80
        with self.assertRaises(ValueError):score_proof('partial',files,case)

    def test_language_labels_recomputed_instead_of_trusting_correct(self):
        folder=ROOT/'language/case-001'
        files=dict(request=folder/'request.json',result=folder/'result.json',catalog=ROOT/'language/catalog.json')
        expected=json.loads((folder/'result.json').read_text(encoding='utf-8'))['case']
        r=score_proof('language',files,expected);self.assertTrue(r['checks']['decision_correct'])

    def test_language_wrong_skill_not_hidden_by_old_correct_flag(self):
        folder=ROOT/'language/case-001'
        d=json.loads((folder/'result.json').read_text(encoding='utf-8'))
        catalog=json.loads((ROOT/'language/catalog.json').read_text(encoding='utf-8'))
        d['result']['skill_id']=next(c['id'] for c in catalog if c['finalGoals']==[1,60,None,None])
        with tempfile.TemporaryDirectory() as tmp:
            dest=Path(tmp)/'result.json';dest.write_text(json.dumps(d))
            r=score_proof('language',dict(request=folder/'request.json',result=dest,catalog=ROOT/'language/catalog.json'),d['case'])
            self.assertFalse(r['checks']['decision_correct'])

    def test_import_and_offline_reaudit_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'campaign'
            p,rows=import_partial(ROOT,out)
            first=summarize(p,rows);second=summarize(*audit_campaign(out))
            self.assertEqual(first,second)
            self.assertEqual(first['stages']['execution']['states']['PASS'],40)
            self.assertEqual(first['stages']['fault']['states']['PASS'],6)
            self.assertEqual(first['stages']['language']['states']['PASS'],16)
            self.assertEqual(first['stages']['teaching']['states']['PASS'],2)
            self.assertEqual(first['stages']['migration']['states']['PASS'],2)

    def test_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileExistsError):import_partial(ROOT,Path(tmp))

    def test_capability_label_cannot_upgrade_multi_page_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'campaign';import_partial(ROOT,out)
            p=json.loads((out/'plan.json').read_text(encoding='utf-8'))
            p['cases'][0]['capabilities']=['exec.singlepage']
            from evaluation_import import dump,sha
            dump(out/'plan.json',p);(out/'plan.sha256').write_text(sha(out/'plan.json'))
            self.assertEqual(summarize(*audit_campaign(out))['cases'][0]['state'],'INVALID')

    def test_sealed_hash_tampering_becomes_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'campaign';import_partial(ROOT,out)
            p=json.loads((out/'plan.json').read_text(encoding='utf-8'))
            path=out/p['cases'][0]['proof']['files']['oracle']
            path.write_text('{}')
            report=summarize(*audit_campaign(out))
            self.assertEqual(report['cases'][0]['state'],'INVALID')

    def test_frozen_plan_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'campaign';import_partial(ROOT,out)
            p=json.loads((out/'plan.json').read_text(encoding='utf-8'));p['cases'].pop()
            (out/'plan.json').write_text(json.dumps(p))
            with self.assertRaises(ValueError):audit_campaign(out)


if __name__=='__main__':unittest.main()
