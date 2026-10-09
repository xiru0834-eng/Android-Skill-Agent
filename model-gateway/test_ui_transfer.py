import copy
import unittest
import json
import tempfile
from pathlib import Path
from collections import Counter
from ui_transfer import make_cases, criteria, verify_context, freeze, score_observation
from named_journey_import import initial_preferences


class UITransferTests(unittest.TestCase):
    def test_frozen_matrix_has_three_identical_repetitions(self):
        cases=make_cases();self.assertEqual(len(cases),36)
        counts=Counter((c['config'],c['skill'],c['condition'],tuple(c['initial'])) for c in cases)
        self.assertEqual(set(counts.values()),{3})
        self.assertEqual(len({c['id'] for c in cases}),36)
        self.assertEqual(cases,make_cases())

    def test_normal_and_negative_not_pooled(self):
        cases=make_cases()
        self.assertEqual(sum(c['config']=='renamed' for c in cases),6)
        self.assertEqual(sum(c['condition']=='all' for c in cases),6)
        self.assertTrue(all(c['expectedReason'].startswith('MISSING:wfOpen') for c in cases if c['config']=='renamed'))

    def base(self):
        return dict(confirmed_success=True,false_success=False,non_target_violation=False,route={'valid':True},
                    evidence_complete=True,unexpectedInputs=0,afterDeadlineInputs=0,post_terminal_inputs=0,extraInputs=0,inputs=4)

    def test_success_cannot_offset_extra_input_or_protected_change(self):
        row=self.base();self.assertTrue(criteria(dict(condition='none'),row))
        row['extraInputs']=1;self.assertFalse(criteria(dict(condition='none'),row))
        row=self.base();row['non_target_violation']=True
        self.assertFalse(criteria(dict(condition='none'),row))

    def test_already_requires_zero_and_negative_requires_no_change(self):
        self.assertFalse(criteria(dict(condition='all'),self.base()))
        row=self.base();row.update(confirmed_success=False,status='UNCONFIRMED',reason='MISSING:wfOpenLamp',inputs=0)
        c=dict(condition='none',expected='UNCONFIRMED',expectedReason='MISSING:wfOpenLamp')
        self.assertTrue(criteria(c,row,state_unchanged=True))
        self.assertFalse(criteria(c,row,state_unchanged=False))
        row['inputs']=1;self.assertFalse(criteria(c,row,state_unchanged=True))

    def test_fixture_difference_must_be_real_and_expected(self):
        c=next(x for x in make_cases() if x['config']=='tablet')
        context=dict(appearance='reordered',size='1600x2560',density='320')
        before=dict(initial=c['initial'],appearance='reordered')
        self.assertTrue(verify_context(c,context,before))
        wrong=copy.deepcopy(context);wrong['size']='1080x2400'
        with self.assertRaises(ValueError):verify_context(c,wrong,before)
        before['appearance']='native'
        with self.assertRaises(ValueError):verify_context(c,context,before)

    def test_freeze_preserves_two_original_packs_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'campaign';freeze(root)
            plan=json.loads((root/'plan.json').read_text(encoding='utf-8'))
            self.assertEqual(len(plan['cases']),36)
            self.assertEqual(plan['phase'],'confirmation')
            self.assertTrue(all(c['dimensions']['steps']==4 for c in plan['cases']))
            with self.assertRaises(FileExistsError):freeze(root)

    def test_adapter_rechecks_real_ledger_and_detects_missing_source(self):
        root=Path(__file__).resolve().parents[1]/'evaluation/partial-workflow/phone-matrix/run-000'
        d={p.stem:json.loads(p.read_text(encoding='utf-8')) for p in root.glob('*.json')}
        d['case']['config']='reference';d['score']['case']=copy.deepcopy(d['case'])
        d['context']=dict(appearance='native',size='1080x2400',density='420')
        d['source']={'skill':copy.deepcopy(d['skill'])}
        for data in [d['before'],d['oracle']]+[x['oracle'] for x in d['audit']]:data['appearance']='native'
        d['persisted']=d['oracle']['events'][-1]['saved']
        self.assertTrue(score_observation(d,d['case'])['checks']['task_confirmed'])
        d['source']['skill']['goal']='modified'
        with self.assertRaises(ValueError):score_observation(d,d['case'])

    def test_new_install_missing_preferences_are_empty_not_forged(self):
        def missing(_):raise RuntimeError('ADB failed: cat: shared_prefs/recorded_workflows.xml: No such file or directory')
        self.assertEqual(initial_preferences('emulator-5554',missing),{})

    def test_import_initial_read_does_not_hide_permission_or_device_errors(self):
        def failed(_):raise RuntimeError('ADB failed: Permission denied')
        with self.assertRaises(RuntimeError):initial_preferences('emulator-5554',failed)
