import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import repair_r3_real_nl as real
from prepare_g1 import save


class RealScorerTest(unittest.TestCase):
    def fixture(self,root):
        selection={'request_id':'abc','status':'invoke','flow_hash':'flow','plan':{},'arguments':[]}
        row={'case':'explicit','flow_hash':'flow','final_status':'SUCCESS',
             'before':{'case_id':'case'},'after':{'case_id':'case','events':[]},
             'ui':{'selection':selection,'ui_audit':[], 'result':{
                 'task_id':'task.abc','flow_hash':'flow','completed_steps':4,'final_observation_complete':True,
                 'verification_result':True,'steps':[{'status':'VERIFIED'}]*4,'latency':{'runtime_ms':7999},
                 'completion_boundary':{'stage':'SERVICE_RECEIPT_READY'}}},
             'assessment':{'passed':True,'false_success':False,'wrong_action':False}}
        save(root/'model-audit/abc.json',{'request_id':'abc','result':{k:v for k,v in selection.items() if k!='request_id'}})
        return row

    def test_valid_full_receipt_and_current_model_evidence(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            real.check_row(root/'explicit.json',self.fixture(root))
            self.assertTrue(json.loads((root/'explicit.json').read_text())['assessment']['audit_complete'])

    def test_expired_incomplete_or_mismatched_positive_stops_before_next(self):
        for mutation in ('late','missing_final','wrong_task','missing_step'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as name:
                root=Path(name);row=self.fixture(root);result=row['ui']['result']
                if mutation=='late':result['latency']['runtime_ms']=8000
                elif mutation=='missing_final':result['final_observation_complete']=False
                elif mutation=='wrong_task':result['task_id']='task.old'
                else:result['steps'].pop()
                with self.assertRaisesRegex(ValueError,'REAL_CASE_FAILED'):
                    real.check_row(root/'failed.json',row)
                stored=json.loads((root/'failed.json').read_text())
                self.assertTrue(stored['assessment']['false_success'])

    def test_missing_model_audit_is_not_safe_pass(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);row=self.fixture(root)
            row['ui']['selection']['request_id']='not-present'
            with self.assertRaises(ValueError):real.check_row(root/'failed.json',row)
            self.assertFalse(row['assessment']['audit_complete'])

    def test_expected_failure_is_preserved_then_stops(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);row=self.fixture(root)
            row['final_status']='BUDGET_EXCEEDED'
            row['assessment']['passed']=False
            with self.assertRaises(ValueError):real.check_row(root/'failed.json',row)
            self.assertTrue((root/'failed.json').exists())

    def test_original_24_cases_not_24_placeholders(self):
        self.assertEqual(sum(n for p,h,n in real.PHASES),24)
        self.assertEqual([n for p,h,n in real.PHASES],[8,8,2,2,2,2])

    def test_closed_native_gate_sends_no_model_command(self):
        with tempfile.TemporaryDirectory() as name:
            with patch.object(real.confirm,'OUT',Path(name)),patch.object(real.confirm,'check_product'),patch.object(real.Batch,'create') as start:
                with self.assertRaisesRegex(ValueError,'NATIVE_PROTECTION_GATE_NOT_RELEASED'):
                    real.run()
                start.assert_not_called()


if __name__=='__main__':unittest.main()
