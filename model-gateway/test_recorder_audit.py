import copy
import json
import tempfile
import unittest
from pathlib import Path
from recorder_audit import inspect

class RecorderAuditTests(unittest.TestCase):
    def fixture(self,root):
        records={'trace.json':dict(traceId='x',source='AUTOMATED',end='REJECTED',error='TIMEOUT'),
                 'audit.json':dict(traceId='x',end='REJECTED',error='TIMEOUT',pending={'id':'wfLampSave'},events=[dict(kind='CLICK',id='wfLampSave')]),
                 'inputs.json':[dict(key='wfLampSave')],
                 'oracle.json':dict(events=[dict(kind='input:wfLampSave',saved=[0,40,0,3])])}
        for key,value in records.items():(root/key).write_text(json.dumps(value),encoding='utf-8')
        return records
    def test_retained_failure_is_auditable(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.fixture(root);self.assertEqual(inspect(root)['status'],'PASS')
    def test_hidden_input_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);data=self.fixture(root);data['oracle.json']['events'].append(dict(kind='input:wfReset'))
            (root/'oracle.json').write_text(json.dumps(data['oracle.json']))
            with self.assertRaises(AssertionError):inspect(root)
    def test_missing_failure_control_is_detected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);data=self.fixture(root);data['audit.json']['pending']=None
            (root/'audit.json').write_text(json.dumps(data['audit.json']))
            with self.assertRaises(AssertionError):inspect(root)
    def test_ambiguity_is_reported_not_guessed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);data=self.fixture(root)
            data['audit.json']['events']=[dict(kind='UNRESOLVED_CLICK',id=None,candidateIds=['wfLampSave','wfFanSave'])]
            (root/'audit.json').write_text(json.dumps(data['audit.json']))
            self.assertEqual(inspect(root)['unresolvedClicks'],1)
