import copy,unittest
from device_stress_audit import inspect_row

def good():
    initial={'bedroom_light.power':'off','bedroom_light.brightnessPercent':20,'bedroom_ac.power':'off','bedroom_ac.temperatureCelsius':20}
    final=dict(initial);final['bedroom_light.brightnessPercent']=50
    event=dict(property='bedroom_light.brightnessPercent',value=50)
    calls=[dict(skill='SetBrightness',args=dict(device='bedroom_light',percent=50))]
    return dict(case=dict(initial=[0,20,0,20],calls=calls,positive=True),before=dict(state=initial,events=[]),after=dict(state=final,events=[event]),
        runtime=dict(calls=calls,initial_state=initial,final_observed_state=final,final_status='SUCCESS',verification_result=True,
            execution_actions=[dict(event,accepted=True)],resolved_element=[dict(property=event['property'],id='edu.sydney.parameterroom:id/psBrightness',**{'class':'android.widget.SeekBar'})]))

class IndependentStressAuditTest(unittest.TestCase):
    def test_good_result(self):self.assertTrue(inspect_row(good())['correct'])
    def test_false_success_oracle(self):
        r=good();r['after']['state']['bedroom_light.brightnessPercent']=20
        self.assertTrue(inspect_row(r)['false_success'])
    def test_target_only_observation_cannot_claim_joint_success(self):
        r=good();r['runtime']['final_observation_complete']=False
        self.assertTrue(inspect_row(r)['false_success'])
    def test_wrong_repeated_input(self):
        r=good();r['after']['events']*=2
        self.assertTrue(inspect_row(r)['wrong_action'])
    def test_missed_unmentioned_change(self):
        r=good();r['after']['state']['bedroom_ac.power']='on'
        self.assertTrue(inspect_row(r)['wrong_action'])
    def test_resolver_wrong_target(self):
        r=good();r['runtime']['resolved_element'][0]['id']='other'
        self.assertEqual(inspect_row(r)['resolver_wrong'],1)
    def test_noop_with_input_is_not_correct(self):
        r=good();r['runtime']['final_status']='NO_ACTION_REQUIRED'
        self.assertFalse(inspect_row(r)['correct'])
    def test_safety_is_not_positive_success(self):
        r=good();r['case'].update(positive=False,expected_status='BLOCKED_BY_OVERLAY',expected_inputs=0)
        r['runtime'].update(final_status='BLOCKED_BY_OVERLAY',execution_actions=[],resolved_element=[]);r['after']=copy.deepcopy(r['before'])
        self.assertTrue(inspect_row(r)['safety_correct']);self.assertFalse(inspect_row(r)['correct'])
    def test_preinput_failure_logged_intent_is_not_a_sent_input(self):
        r=good();r['case'].update(positive=False,expected_status='ENVIRONMENT_ERROR',expected_inputs=0,expected_attempts=1)
        r['runtime'].update(final_status='ENVIRONMENT_ERROR',resolved_element=[])
        r['runtime']['execution_actions'][0].pop('accepted');r['after']=copy.deepcopy(r['before'])
        self.assertTrue(inspect_row(r)['safety_correct'])
    def test_input_rejection_receipt_is_not_an_environment_failure(self):
        r=good();r['case'].update(positive=False,fault='input_reject',expected_status='FAILED',expected_inputs=0)
        r['runtime'].update(final_status='FAILED',resolved_element=[])
        r['runtime']['execution_actions'][0]['accepted']=False;r['after']=copy.deepcopy(r['before'])
        self.assertTrue(inspect_row(r)['safety_correct'])
if __name__=='__main__':unittest.main()
