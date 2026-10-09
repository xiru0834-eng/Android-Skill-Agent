import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from accuracy_confirmation import build_cases
from accuracy_v2 import cases_for,measure,summarize,run_batch
from test_selection_accuracy import response
from compiler import MODEL,ModelError
from workflow_experiment import write
from selection_deadline import SelectionBudget

BASE=[dict(id=str(i)*64,name=n,goal='Recorded immutable target.',finalGoals=g) for i,n,g in [
 (1,'阅读60 / Reading60',[1,60,1,1]),(2,'明亮80 / Bright80',[1,80,1,3]),
 (3,'只灯60 / LampOnly60',[1,60,None,None]),(4,'只风扇低档 / FanOnlyLow',[None,None,1,1]),
 (5,'全开100',[1,100,1,1])]]


class AccuracyV2Tests(unittest.TestCase):
    def test_balanced_distinct_new_texts_and_valid_identity_labels(self):
        data=cases_for(BASE);self.assertEqual(len(data),60)
        self.assertEqual(len({c['text'] for c in data}),60)
        self.assertFalse({c['text'] for c in data}&{c['text'] for c in build_cases(BASE)})
        for language in ['zh','en']:
            part=[c for c in data if c['language']==language]
            self.assertEqual(len(part),30);self.assertEqual(sum(c['expected'] is not None for c in part),15)
        for c in data:
            if c['expected']:self.assertIn(c['expected'],{s['id'] for s in c['skills']})

    def test_audit_stores_requests_and_two_response_stages(self):
        case=next(c for c in cases_for(BASE) if c['caseId']=='preserve-fan-en')
        now=[0.]
        def transport(body,timeout):
            if body['model']==MODEL:return dict(draft=dict(status='invoke',skill_id='3'*64,message='review'),returned_model=MODEL)
            now[0]=.5
            options=[f'skill_{i}' for i in range(5)]+['clarify','reject']
            from jev_selection import MODEL as JEV
            return dict(model=JEV,answers=dict(selection=dict(type='choice',choice='skill_2',confidence=.85,
                probabilities={k:.94 if k=='skill_2' else .01 for k in options})))
        with tempfile.TemporaryDirectory() as temp:
            row=measure('H2',case,Path(temp),transport=transport,budget=SelectionBudget(8,clock=lambda:now[0]))
            self.assertTrue(row['correct']);self.assertEqual(row['remoteCalls'],2)
            self.assertLess(row['calls'][1]['timeoutSeconds'],row['calls'][0]['timeoutSeconds'])
            self.assertEqual(len(list(Path(temp).glob('response-*.json'))),2)

    def test_format_error_does_not_count_as_safe_negative(self):
        case=next(c for c in cases_for(BASE) if c['caseId']=='explanation-en')
        row=measure('H2',case,transport=lambda body,timeout:dict(bad=True))
        self.assertFalse(row['correct']);self.assertEqual(row['failureClass'],'availability')
        self.assertEqual(row['remoteCalls'],1)

    def test_unsafe_suggestion_blocks_gate(self):
        cases=cases_for(BASE);rows=[]
        for strategy in ['G','H2']:
            for repeat in range(3):
                for c in cases:
                    selection=dict(status='invoke' if c['expected'] else 'reject',skill_id=c['expected'],message='test')
                    row=dict(strategy=strategy,case=c,repeat=repeat,available=True,selection=selection,remoteCalls=0,
                        inputTokens=0,outputTokens=0,ms=0,correct=True,unsafeSuggestion=False)
                    rows.append(row)
        protocol=dict(cases=cases,trials=[None]*360)
        self.assertTrue(summarize(rows,protocol)['gatePassed'])
        rows[-1].update(correct=False,unsafeSuggestion=True)
        self.assertFalse(summarize(rows,protocol)['gatePassed'])

    def test_account_error_counter_survives_batch_boundary(self):
        case=cases_for(BASE)[0]
        protocol=dict(cases=[case],trials=[dict(index=0,repeat=i,strategy='G') for i in range(4)],
            maxRemoteCalls=10,batchSize=2)
        def failed(strategy,c,folder):
            return dict(strategy=strategy,case=c,available=False,error='HTTP_429',remoteCalls=1,
                inputTokens=0,outputTokens=0,ms=0,correct=False,unsafeSuggestion=False,failureClass='availability')
        with tempfile.TemporaryDirectory() as temp,patch('accuracy_v2.verify_protocol'):
            out=Path(temp);write(out/'protocol.json',protocol)
            run_batch(out,failed);run_batch(out,failed)
            self.assertEqual(len(json.loads((out/'results.json').read_text(encoding='utf-8'))),3)
            self.assertTrue((out/'stopped.json').exists())
            with self.assertRaisesRegex(ValueError,'STOPPED'):run_batch(out,failed)

    def test_orphan_trial_is_not_silently_repeated(self):
        with tempfile.TemporaryDirectory() as temp,patch('accuracy_v2.verify_protocol'):
            out=Path(temp);write(out/'protocol.json',dict(cases=[],trials=[],maxRemoteCalls=540,batchSize=60))
            (out/'trials/orphan').mkdir(parents=True)
            with self.assertRaisesRegex(ValueError,'INCOMPLETE'):run_batch(out,lambda *a:self.fail('called'))


if __name__=='__main__':unittest.main()
