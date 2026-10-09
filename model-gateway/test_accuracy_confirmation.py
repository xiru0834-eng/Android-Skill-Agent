import copy
import tempfile
import unittest
from pathlib import Path
from test_skill_selection import CATALOG
from accuracy_confirmation import build_cases, adjudicate, aggregate, freeze, verify_protocol, run_batch


def skills():
    return CATALOG + [
        dict(id='c'*64,name='只灯60 / LampOnly60',goal='Lamp only.',finalGoals=[1,60,None,None]),
        dict(id='d'*64,name='只风扇低档 / FanOnlyLow',goal='Fan only.',finalGoals=[None,None,1,1]),
        dict(id='e'*64,name='双设备100 / Both100',goal='Both.',finalGoals=[1,100,1,1])]


class AccuracyConfirmationTests(unittest.TestCase):
    def test_matrix_balances_language_scope_and_unique_text(self):
        cases=build_cases(skills())
        self.assertEqual(len(cases),60)
        self.assertEqual(sum(c['expected'] is not None for c in cases),30)
        self.assertEqual(sum(c['language']=='zh' for c in cases),30)
        self.assertEqual(len({c['text'] for c in cases}),60)
        self.assertEqual(len({c['conceptId'] for c in cases}),30)
        self.assertEqual(len({c['category'] for c in cases}),10)
        for case in cases:
            if case['expected'] is not None:
                self.assertIn(case['expected'],[s['id'] for s in case['skills']])

    def test_failure_is_not_safe_rejection(self):
        case=next(c for c in build_cases(skills()) if c['expected'] is None)
        row=adjudicate(dict(case=case,available=False,selection={},ms=20,remoteCalls=1,inputTokens=None,outputTokens=None))
        self.assertFalse(row['correct'])
        self.assertFalse(row['unsafeSuggestion'])
        self.assertEqual(row['failureClass'],'availability')

    def test_false_invoke_and_valid_abstention_remain_different(self):
        cases=build_cases(skills());pos=next(c for c in cases if c['expected']);neg=next(c for c in cases if not c['expected'])
        def row(case,status,identity):
            return adjudicate(dict(case=case,available=True,selection=dict(status=status,skill_id=identity),ms=2,
                remoteCalls=0,inputTokens=0,outputTokens=0))
        self.assertEqual(row(pos,'clarify',None)['failureClass'],'valid_abstention')
        self.assertEqual(row(neg,'invoke','a'*64)['failureClass'],'false_invoke')
        self.assertTrue(row(neg,'invoke','a'*64)['unsafeSuggestion'])

    def test_unrun_trials_never_look_like_all_pass(self):
        with tempfile.TemporaryDirectory() as root:
            protocol=freeze(Path(root)/'batch',skills())
            summary=aggregate([],protocol)
            self.assertEqual(summary['planned'],360)
            self.assertEqual(summary['notRun'],360)
            self.assertFalse(summary['gatePassed'])

    def test_freeze_verifies_snapshot_and_rejects_modified_labels(self):
        with tempfile.TemporaryDirectory() as root:
            out=Path(root)/'batch';protocol=freeze(out,skills())
            verify_protocol(out,protocol)
            changed=copy.deepcopy(protocol);changed['cases'][0]['expected']=None
            with self.assertRaises(ValueError):verify_protocol(out,changed)
            with self.assertRaises(FileExistsError):freeze(out,skills())

    def test_batches_resume_without_repeating_old_calls(self):
        with tempfile.TemporaryDirectory() as root:
            out=Path(root)/'batch';freeze(out,skills());calls=[]
            def fake(strategy,case,folder):
                calls.append(case['caseId'])
                return dict(strategy=strategy,available=True,selection=dict(
                    status='invoke' if case['expected'] else 'reject',skill_id=case['expected']),
                    ms=1,remoteCalls=1,inputTokens=1,outputTokens=1,route='remote')
            first=run_batch(out,measure_fn=fake)
            second=run_batch(out,measure_fn=fake)
            self.assertEqual(first['completed'],60)
            self.assertEqual(second['completed'],120)
            self.assertEqual(len(calls),120)

    def test_three_account_errors_stop_and_cannot_auto_resume(self):
        with tempfile.TemporaryDirectory() as root:
            out=Path(root)/'batch';freeze(out,skills());calls=[]
            def fake(strategy,case,folder):
                calls.append(1)
                return dict(strategy=strategy,available=False,error='HTTP_429',ms=1,
                    remoteCalls=1,inputTokens=None,outputTokens=None,route='remote')
            self.assertEqual(run_batch(out,measure_fn=fake)['completed'],3)
            with self.assertRaises(ValueError):run_batch(out,measure_fn=fake)
            self.assertEqual(len(calls),3)

    def test_account_error_streak_survives_batch_boundary(self):
        with tempfile.TemporaryDirectory() as root:
            out=Path(root)/'batch';freeze(out,skills());calls=[]
            def fake(strategy,case,folder):
                calls.append(1);failed=59<=len(calls)<=61
                return dict(strategy=strategy,available=not failed,**(dict(error='HTTP_429') if failed else
                    dict(selection=dict(status='invoke' if case['expected'] else 'reject',skill_id=case['expected']))),
                    ms=1,remoteCalls=1,inputTokens=1,outputTokens=1,route='remote')
            run_batch(out,measure_fn=fake)
            self.assertEqual(run_batch(out,measure_fn=fake)['completed'],61)


if __name__=='__main__':unittest.main()
