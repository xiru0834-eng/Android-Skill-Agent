import copy
import unittest

from evaluation_framework import compare_reports, ratio, summarize, validate_plan


def plan(n=1, stage='execution'):
    return dict(schema=1, framework='framework-1', campaign='test', phase='development',
                variant='A', comparison=dict(dataset='fixed', app='apphash', device='phone',
                                            display='1080x2400@420', budget_ms=30000,
                                            auditor='framework-1', changed_factor='executor'),
                capabilities=[dict(id='exec.partial', label='Partial target')],
                cases=[dict(id=str(i), stage=stage, family='one', repeat=i,
                            capabilities=['exec.partial'], environment='phone',
                            expected='complete', dimensions=dict(pages=2, steps=4)) for i in range(n)])


def observed(case_id='0', **metrics):
    base=dict(actual_success=True, reported_success=True, non_target_violation=False,
              input_violations=0, post_terminal_inputs=0, extra_inputs=0, input_count=4,
              timings=dict(execution_ms=100, model_ms=None, e2e_ms=None))
    base.update(metrics)
    return dict(case_id=case_id, state='SCORED', checks=dict(audit_complete=True,
                task_confirmed=base['actual_success'] and base['reported_success'],
                protected=not base['non_target_violation'], input_safe=base['input_violations']==0,
                route=True), metrics=base, evidence_basis='independent_ledger')


class EvaluationCoreTests(unittest.TestCase):
    def test_zero_denominator_is_unknown(self):
        self.assertIsNone(ratio(0, 0)['value'])
        self.assertIsNone(ratio(0, 0)['wilson95'])

    def test_all_pass_interval_does_not_claim_certainty(self):
        r=ratio(12, 12)
        self.assertAlmostEqual(r['wilson95'][0], .75750599, places=6)
        self.assertEqual(r['wilson95'][1], 1)

    def test_duplicate_plan_id_rejected(self):
        p=plan(2);p['cases'][1]['id']='0'
        with self.assertRaises(ValueError):validate_plan(p)

    def test_duplicate_family_repeat_rejected_even_if_id_differs(self):
        p=plan(2);p['cases'][1]['repeat']=0
        with self.assertRaises(ValueError):validate_plan(p)

    def test_blocked_request_latency_is_retained(self):
        r=summarize(plan(),[dict(case_id='0',state='BLOCKED',metrics=dict(timings=dict(model_ms=55)))])
        self.assertEqual(r['stages']['execution']['timings']['model_ms']['p50'],55)

    def test_unknown_capability_rejected(self):
        p=plan();p['cases'][0]['capabilities']=['invented']
        with self.assertRaises(ValueError):validate_plan(p)

    def test_already_at_target_capability_requires_zero_inputs(self):
        p=plan();p['capabilities']=[dict(id='exec.zero',label='Already at target')]
        p['cases'][0]['capabilities']=['exec.zero']
        self.assertEqual(summarize(p,[observed()])['cases'][0]['state'],'FAIL')

    def test_duplicate_observation_rejected(self):
        with self.assertRaises(ValueError):summarize(plan(),[observed(),observed()])

    def test_observation_outside_plan_rejected(self):
        with self.assertRaises(ValueError):summarize(plan(),[observed('9')])

    def test_not_run_and_blocked_stay_in_planned_denominator(self):
        r=summarize(plan(3),[observed(),dict(case_id='1',state='BLOCKED',error='boot')])
        s=r['stages']['execution']
        self.assertEqual(s['pass_planned']['denominator'],3)
        self.assertEqual(s['pass_scored']['denominator'],1)
        self.assertEqual(s['states']['NOT_RUN'],1)
        self.assertEqual(s['states']['BLOCKED'],1)

    def test_missing_audit_is_invalid(self):
        o=observed();del o['checks']['audit_complete']
        self.assertEqual(summarize(plan(),[o])['cases'][0]['state'],'INVALID')

    def test_false_success_and_failed_latency_remain_visible(self):
        o=observed(actual_success=False,reported_success=True,timings=dict(execution_ms=30000))
        s=summarize(plan(),[o])['stages']['execution']
        self.assertEqual(s['states']['FAIL'],1)
        self.assertEqual(s['false_success']['numerator'],1)
        self.assertEqual(s['timings']['execution_ms']['p95'],30000)

    def test_check_contradicting_actual_state_is_invalid(self):
        o=observed(actual_success=False);o['checks']['task_confirmed']=True
        self.assertEqual(summarize(plan(),[o])['cases'][0]['state'],'INVALID')

    def test_non_target_violation_cannot_be_offset_by_completion(self):
        r=summarize(plan(),[observed(non_target_violation=True)])
        self.assertEqual(r['cases'][0]['state'],'FAIL')
        self.assertIn('non_target_violation',r['alerts'])

    def test_extra_inputs_fail_even_when_final_goal_is_met(self):
        o=observed(extra_inputs=1);o['checks']['input_safe']=False
        r=summarize(plan(),[o])
        self.assertEqual(r['cases'][0]['state'],'FAIL')
        self.assertIn('input_violation_or_extra_input',r['alerts'])

    def test_fault_stop_not_in_execution_completion(self):
        p=plan(stage='fault')
        o=dict(case_id='0',state='SCORED',checks=dict(audit_complete=True,expected_stop=True,
             protected=True,input_safe=True),metrics=dict(actual_success=False,reported_success=False))
        r=summarize(p,[o]);self.assertNotIn('execution',r['stages'])
        self.assertEqual(r['stages']['fault']['states']['PASS'],1)

    def test_unmeasured_capability_is_visible(self):
        p=plan();p['capabilities'].append(dict(id='human',label='Human teaching'))
        c=summarize(p,[observed()])['capabilities']['human']
        self.assertEqual(c['status'],'NOT_TESTED')

    def test_repetition_does_not_pool_different_environment(self):
        p=plan(3);p['cases'][2]['environment']='emulator'
        c=summarize(p,[observed(str(i)) for i in range(3)])['capabilities']['exec.partial']
        self.assertEqual(c['minimum_repeats'],1)
        self.assertEqual(c['evidence_level'],'SMALL_SAMPLE')

    def test_mixed_repeat_outcomes_are_captured(self):
        r=summarize(plan(2),[observed(),observed('1',actual_success=False,reported_success=False)])
        self.assertEqual(r['capabilities']['exec.partial']['inconsistent_families'],1)

    def test_bad_timing_and_boolean_input_count_are_rejected(self):
        for change in [dict(timings=dict(execution_ms=float('nan'))),dict(input_count=True)]:
            with self.assertRaises(ValueError):summarize(plan(),[observed(**change)])

    def test_pairing_rejects_environment_change(self):
        a=summarize(plan(),[observed()]);p=plan();p['comparison']['device']='emulator'
        b=summarize(p,[observed()])
        self.assertEqual(compare_reports(a,b)['status'],'INCOMPARABLE')

    def test_old_summary_without_trial_records_is_not_a_paired_report(self):
        self.assertEqual(compare_reports(summarize(plan(),[observed()]),dict(passed=12))['status'],'INCOMPARABLE')

    def test_pairing_reports_discordant_outcomes(self):
        a=summarize(plan(2),[observed(),observed('1',actual_success=False,reported_success=False)])
        p=plan(2);p['variant']='B'
        b=summarize(p,[observed(actual_success=False,reported_success=False),observed('1')])
        r=compare_reports(a,b)
        self.assertEqual(r['status'],'DESCRIPTIVE_PAIRED')
        self.assertEqual((r['a_only'],r['b_only']),(1,1))

    def test_pairing_rejects_different_cases_and_missing_metadata(self):
        a=summarize(plan(),[observed()]);b=summarize(plan(2),[observed(),observed('1')])
        self.assertEqual(compare_reports(a,b)['status'],'INCOMPARABLE')
        a['comparison']={};self.assertEqual(compare_reports(a,a)['status'],'INCOMPARABLE')


if __name__=='__main__':unittest.main()
