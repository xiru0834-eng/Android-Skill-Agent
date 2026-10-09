"""Strict receipts, original judge counterexamples and evidence-pipeline E2E."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from test_task3_audit import complete
from task5_evidence import ReceiptReader, judge_run, received_language, replay_verify


class EvidenceTests(unittest.TestCase):
    def test_non_json_guide_and_xml_receipts_replay_as_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'source';root.mkdir()
            (root/'guide.txt').write_text('1. Save lamp settings',encoding='utf-8')
            (root/'ui.xml').write_text('<hierarchy/>',encoding='utf-8')
            reader=ReceiptReader(root);reader.raw('guide.txt');reader.raw('ui.xml')
            target=Path(tmp)/'copy';reader.snapshot(target)
            self.assertTrue(replay_verify(target,reader.receipts)['valid'])

    def test_reader_hash_snapshot_relocation_and_tamper(self):
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'source';source.mkdir();(source/'x.json').write_text('{"a":1}',encoding='utf-8')
            reader=ReceiptReader(source);self.assertEqual(reader.read('x.json'),{'a':1})
            snapshot=Path(tmp)/'copy';reader.snapshot(snapshot)
            self.assertTrue(replay_verify(snapshot,reader.receipts)['valid'])
            self.assertEqual(ReceiptReader(snapshot).read('x.json'),{'a':1})
            (snapshot/'x.json').write_text('{"a":2}',encoding='utf-8')
            self.assertFalse(replay_verify(snapshot,reader.receipts)['valid'])

    def test_reader_rejects_traversal_sensitive_json_and_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'bad.json').write_text('{"pairing":"private"}')
            reader=ReceiptReader(root)
            for name in ['../x.json','bad.json']:
                with self.subTest(name=name),self.assertRaises(ValueError):reader.read(name)
            with self.assertRaises(FileExistsError):reader.snapshot(root)

    def test_receipt_names_and_bytes_are_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'x.json').write_bytes(b'{}')
            reader=ReceiptReader(root);reader.read('x.json')
            self.assertEqual(reader.receipts['x.json']['byteCount'],2)
            (root/'x.json').write_bytes(b'{"new":1}')
            with self.assertRaises(ValueError):reader.read('x.json')

    def test_normal_raw_judge_does_not_accept_missing_audit(self):
        data=complete();self.assertEqual(judge_run(data)['state'],'PASS')
        data[5].pop();r=judge_run(data)
        self.assertEqual(r['state'],'UNVERIFIED');self.assertFalse(r['falseSuccess'])

    def test_counterexamples_preserve_actual_outcomes_and_missing(self):
        for kind in ['disk','late','source','non_target','duplicate_audit','no_terminal']:
            data=copy.deepcopy(complete())
            if kind=='disk':data[6][1]=40
            elif kind=='late':data[2]['deadlineMs']=399
            elif kind=='source':data[2]['actions'][0]['sourceIndex']=2
            elif kind=='non_target':data[3]['events'][1]['draft'][2]=1
            elif kind=='duplicate_audit':data[5]=[data[5][0]]*3
            else:data[4].pop()
            with self.subTest(kind=kind):self.assertNotEqual(judge_run(data)['state'],'PASS')

    def test_language_uses_raw_response_not_correct_flag(self):
        skill=dict(id='a'*64,name='Lamp',goal='Lamp 60',finalGoals=[1,60,None,None])
        case=dict(caseId='x',expected='a'*64,skills=[skill],acceptableStatuses=['invoke'])
        row=dict(case=case,correct=True,repeat=0,selection=dict(status='invoke',skill_id='a'*64,message='OK'),ms=100,
                 remoteCalls=1,calls=[dict(provider='GPT',model='model',outcome='RETURNED')])
        response=dict(draft=dict(status='reject',skill_id=None,message='No'),returned_model='model',request_id='resp_x')
        request=dict(model='model',input=[dict(content=json.dumps(dict(text='x',skills=[skill])))])
        case['text']='x';row['case']=case
        r=received_language(case,row,request,response,'model')
        self.assertFalse(r['correct']);self.assertFalse(r['qualified'])
        row['selection']=response['draft'];r=received_language(case,row,request,response,'model')
        self.assertFalse(r['correct']);self.assertTrue(r['qualified'])

    def test_language_wrong_model_budget_and_bool_latency_rejected(self):
        skill=dict(id='a'*64,name='Lamp',goal='Lamp 60',finalGoals=[1,60,None,None])
        c=dict(caseId='x',text='x',expected='a'*64,skills=[skill],acceptableStatuses=['invoke'])
        draft=dict(status='invoke',skill_id='a'*64,message='OK')
        row=dict(case=c,selection=draft,ms=100,remoteCalls=1,calls=[dict(provider='GPT',model='model',outcome='RETURNED')])
        req=dict(model='model',input=[dict(content=json.dumps(dict(text='x',skills=[skill])))])
        resp=dict(draft=draft,returned_model='model',request_id='resp_x')
        self.assertTrue(received_language(c,row,req,resp,'model')['correct'])
        for kind in ['model','latency','calls']:
            a,b=copy.deepcopy(row),copy.deepcopy(resp)
            if kind=='model':b['returned_model']='other'
            elif kind=='latency':a['ms']=True
            else:a['remoteCalls']=2
            with self.subTest(kind=kind):self.assertFalse(received_language(c,a,req,b,'model')['qualified'])

    def test_correct_but_late_language_response_does_not_pass(self):
        skill=dict(id='a'*64,name='Lamp',goal='Lamp 60',finalGoals=[1,60,None,None])
        c=dict(caseId='x',text='x',expected='a'*64,skills=[skill],acceptableStatuses=['invoke'])
        draft=dict(status='invoke',skill_id='a'*64,message='OK')
        row=dict(case=c,selection=draft,ms=8000,remoteCalls=1,calls=[dict(provider='GPT',model='m',outcome='RETURNED')])
        req=dict(model='m',input=[dict(content=json.dumps(dict(text='x',skills=[skill])))])
        resp=dict(draft=draft,returned_model='m',request_id='resp_x')
        result=received_language(c,row,req,resp,'m')
        self.assertTrue(result['qualified']);self.assertFalse(result['correct']);self.assertFalse(result['withinBudget'])
