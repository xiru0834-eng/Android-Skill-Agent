import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from evaluation_cli import audit_to, create_plan, csv_cell, write_report
from evaluation_framework import summarize
from evaluation_import import RUN_FILES, audit_campaign, dump, import_partial, sha

ROOT=Path(__file__).resolve().parents[1]/'evaluation/partial-workflow'


class EvaluationCliTests(unittest.TestCase):
    def test_csv_formula_is_not_executable(self):
        self.assertEqual(csv_cell('=SUM(A1)'),"'=SUM(A1)")
        self.assertEqual(csv_cell(12),12)

    def test_future_plan_reports_not_run_until_evidence_arrives(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'new';create_plan(root)
            report=summarize(*audit_campaign(root))
            self.assertEqual(report['stages']['execution']['states']['NOT_RUN'],3)
            self.assertIsNone(report['stages']['execution']['pass_scored']['value'])

    def test_custom_definition_can_freeze_another_campaign(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'sample';p=create_plan(source);p['variant']='candidate'
            config=Path(tmp)/'definition.json';config.write_text(json.dumps(p))
            out=Path(tmp)/'custom';create_plan(out,config)
            self.assertEqual(audit_campaign(out)[0]['variant'],'candidate')

    def test_report_files_and_per_environment_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';p,o=import_partial(ROOT,root);write_report(root,p,o)
            result=json.loads((root/'report.json').read_text(encoding='utf-8'))
            self.assertEqual(len(result['stages']['execution']['environments']),3)
            with (root/'cases.csv').open(encoding='utf-8-sig',newline='') as f:
                rows=list(csv.DictReader(f))
            self.assertEqual(len(rows),68)
            fault=next(r for r in rows if r['id']=='faults.001')
            self.assertEqual(fault['reported_reason'],'AMBIGUOUS:wfLampPower')
            self.assertTrue(fault['failure_step'])
            self.assertIn('未测试',(root/'report.md').read_text(encoding='utf-8'))

    def test_report_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';p,o=import_partial(ROOT,root);write_report(root,p,o)
            with self.assertRaises(FileExistsError):write_report(root,p,o)

    def test_audit_export_outside_proof_directory_is_independently_reauditable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';p=create_plan(root)
            source=ROOT/'phone-matrix/run-000'
            expected=json.loads((source/'case.json').read_text(encoding='utf-8'))
            case=p['cases'][0];p['cases']=[case]
            case['dimensions']['initial']=expected['initial']
            case['proof']['expected']=expected
            case['proof']['files']={k:f'run-000/{k}.json' for k in RUN_FILES}
            folder=root/'run-000';folder.mkdir()
            for name in RUN_FILES:shutil.copyfile(source/(name+'.json'),folder/(name+'.json'))
            (folder/'diagnosis.json').write_text('{}')
            dump(root/'plan.json',p);(root/'plan.sha256').write_text(sha(root/'plan.json'))
            dump(root/'evidence-sha256.json',{str(f.relative_to(root)).replace(chr(92),'/'):sha(f) for f in folder.glob('*.json')})
            first=audit_to(root,Path(tmp)/'report')
            self.assertEqual(first['stages']['execution']['states']['PASS'],1)
            self.assertEqual(first,summarize(*audit_campaign(Path(tmp)/'report')))
            self.assertEqual((Path(tmp)/'report/run-000/diagnosis.json').read_bytes(),b'{}')

    def test_confirmation_report_does_not_describe_new_trials_as_historical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';p=create_plan(root);p['phase']='confirmation'
            write_report(root,p,[])
            text=(root/'report.md').read_text(encoding='utf-8')
            self.assertNotIn('本集合是历史导入',text)
            self.assertIn('证据路径',text)

    def test_export_rejects_hash_paths_outside_campaign(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';create_plan(root)
            outside=Path(tmp)/'outside.json';outside.write_text('{}')
            dump(root/'evidence-sha256.json',{'../outside.json':sha(outside)})
            with self.assertRaises(ValueError):audit_to(root,Path(tmp)/'report')


if __name__=='__main__':unittest.main()
