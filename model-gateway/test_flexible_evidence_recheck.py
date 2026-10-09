import json
import tempfile
import unittest
from pathlib import Path
import test_flexible_device_score as score_fixtures
from flexible_evidence_recheck import recheck
from test_flexible_workflow import trace


class EvidenceRecheckTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.batch=Path(self.temp.name)/'batch';self.recording=self.batch/'brightness-recording'
        self.run=self.batch/'brightness-normal-0';self.recording.mkdir(parents=True);self.run.mkdir()
        fixture=score_fixtures.ScoreTests();fixture.setUp()
        source=trace(['wfOpenLamp','wfLampValue60','wfLampSave'])
        from workflow_contract import compile_evidence
        skill=compile_evidence(source)
        fixture.result['traceSha256']=skill['traceSha256']
        fixture.oracle.update(caseId='case1',initial=fixture.initial)
        for i,event in enumerate(fixture.journal,1):event['seq']=i
        values=dict(protocol=dict(name='brightness',caseId='case1',initial=fixture.initial,fault='normal',modelCalls=0),
                    result=fixture.result,oracle=fixture.oracle,journal=fixture.journal,persistent='0,60,0,3')
        for name,value in values.items():self.write(self.run/(name+'.json'),value)
        self.write(self.recording/'trace.json',source);self.write(self.recording/'skill.json',skill)
    def write(self,path,value):path.write_text(json.dumps(value),encoding='utf-8')
    def change(self,name,edit):
        path=self.run/(name+'.json');value=json.loads(path.read_text(encoding='utf-8'));edit(value);self.write(path,value)
    def test_happy_evidence_hashes_and_no_new_execution_credit(self):
        result=recheck([self.batch]);self.assertEqual(result['summary']['positivePassed'],1)
        self.assertEqual(result['summary']['newDeviceExecutions'],0)
        self.assertEqual(len(result['rows'][0]['sha256']),7)
    def test_wrong_skill_hash_rejected(self):
        self.change('result',lambda value:value.update(traceSha256='0'*64))
        with self.assertRaisesRegex(ValueError,'Wrong skill'):recheck([self.batch])
    def test_wrong_oracle_case_rejected(self):
        self.change('oracle',lambda value:value.update(caseId='different'))
        with self.assertRaisesRegex(ValueError,'Wrong oracle case'):recheck([self.batch])
    def test_persistent_disagreement_rejected(self):
        self.write(self.run/'persistent.json','0,40,0,3')
        with self.assertRaisesRegex(ValueError,'Persistent state'):recheck([self.batch])
    def test_restored_wrong_field_remains_a_failed_assessment(self):
        self.change('oracle',lambda value:value['events'][1].update(draft=[1,40,0,3]))
        result=recheck([self.batch]);self.assertEqual(result['summary']['positivePassed'],0)
        self.assertEqual(result['summary']['falseSuccess'],1)
    def test_duplicate_batches_do_not_inflate_sample_count(self):
        with self.assertRaisesRegex(ValueError,'Duplicate execution'):recheck([self.batch,self.batch])


if __name__=='__main__':unittest.main()
