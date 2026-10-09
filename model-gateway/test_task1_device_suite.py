import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import task1_device_suite
from task1_device_suite import make_execution_cases, initial_for, execution_verdict, injected_preview
from selection_deadline import SelectionBudget


class Task1DeviceSuiteTests(unittest.TestCase):
    def test_display_failure_keeps_partial_case_counts_and_restores_parameters(self):
        def failed_run(serial,out,*args):
            out.mkdir()
            (out/'summary.json').write_text(json.dumps(dict(planned=24,attempted=1,passed=0,failed=1,notRun=23,harnessErrors=0)),encoding='utf-8')
            raise AssertionError('observed missing preview')
        with tempfile.TemporaryDirectory() as folder,patch('task1_device_suite.display',return_value={'size':'Physical size: 720x1280','density':'Physical density: 240'}),patch('task1_device_suite.adb',return_value='1.0'),patch('task1_device_suite.restore_display') as restore,patch('task1_device_suite.time.sleep'),patch('task1_device_suite.entry_run',side_effect=failed_run):
            out=Path(folder)/'batch'
            with self.assertRaisesRegex(AssertionError,'missing preview'):task1_device_suite.display_suite(out)
            summary=json.loads((out/'summary.json').read_text(encoding='utf-8'))
            self.assertEqual(summary['attempted'],1)
            self.assertEqual(summary['failed'],1)
            self.assertEqual(summary['notRun'],95)
            self.assertTrue(summary['restored'])
            restore.assert_called_once()

    def test_injected_transport_accepts_real_budget_keyword_contract(self):
        self.assertEqual(injected_preview('saved',[{'name':'saved','id':'a'*64}],SelectionBudget(1))['skill_id'],'a'*64)
        with self.assertRaisesRegex(RuntimeError,'CATALOG_NAME_NOT_UNIQUE'):
            injected_preview('missing',[{'name':'saved','id':'a'*64}],SelectionBudget(1))
    def test_frozen_normal_and_fault_denominators(self):
        rows=make_execution_cases()
        self.assertEqual(len(rows),75)
        self.assertEqual(sum(c['suite']=='normal' for c in rows),45)
        self.assertEqual(sum(c['suite']=='fault' and c['automatable'] for c in rows),12)
        self.assertEqual(len({c['caseId'] for c in rows}),75)

    def test_initials_preserve_null_and_differ_for_requested_fields(self):
        goal=[1,60,None,None]
        self.assertEqual(initial_for(goal,'all'),[1,60,0,3])
        self.assertEqual(initial_for(goal,'none'),[0,40,0,3])
        self.assertEqual(initial_for(goal,'partial'),[1,40,0,3])

    def test_negative_safe_stop_is_not_task_completion(self):
        correct=dict(correctCompletion=True,falseSuccess=False,untouched=True,status='SUCCEEDED')
        stopped=dict(correctCompletion=False,falseSuccess=False,untouched=True,status='UNCONFIRMED')
        self.assertEqual(execution_verdict(correct,False,True,True),'PASS')
        self.assertEqual(execution_verdict(stopped,True,True,True),'PASS')
        self.assertEqual(execution_verdict(stopped,False,True,True),'FAIL')
        self.assertEqual(execution_verdict(correct,True,True,True),'FAIL')
        self.assertEqual(execution_verdict(stopped,True,False,True),'FAIL')


if __name__=='__main__':unittest.main()
