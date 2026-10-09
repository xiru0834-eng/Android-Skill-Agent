import copy
import unittest
from parameter_calls import build_request, validate_calls, validate_catalog

CATALOG=[dict(device='bedroom_light',skills=['SetPower','SetBrightness'],values=[20,40,60,80,100]),dict(device='bedroom_fan',skills=['SetPower','SetFanSpeed'],values=[1,2,3])]
def result(skill='SetBrightness',device='bedroom_light',**args):
    return dict(status='invoke',message='Review before execution',calls=[dict(skill=skill,args=dict(device=device,**(args or dict(percent=80))))])

class ParameterCallsTests(unittest.TestCase):
    def test_one_request_contains_skills_and_parameters_no_ui_ids(self):
        request=build_request('把卧室灯调到80%',CATALOG)
        self.assertEqual(request['text']['format']['type'],'json_schema')
        self.assertTrue(request['text']['format']['strict'])
        self.assertFalse(request['store'])
        self.assertNotIn('wfLamp',str(request))
    def test_numeric_and_power_calls(self):
        for n in [20,40,60,80,100]:self.assertEqual(validate_calls(result(percent=n),CATALOG)['calls'][0]['args']['percent'],n)
        for state in ['on','off']:validate_calls(result('SetPower',state=state),CATALOG)
        for level in [1,2,3]:validate_calls(result('SetFanSpeed','bedroom_fan',level=level),CATALOG)
    def test_invalid_values_and_types(self):
        for n in [0,55,101,-1,True,80.0,'80',None]:
            with self.subTest(n=n),self.assertRaises(ValueError):validate_calls(result(percent=n),CATALOG)
    def test_unknown_or_wrong_device(self):
        for r in [result('SetTemperature','bedroom_ac',temperature=28),result('SetPower','living_room_light',state='on'),result('SetBrightness','bedroom_fan',percent=80)]:
            with self.assertRaises(ValueError):validate_calls(r,CATALOG)
    def test_extra_fields_and_empty_invoke(self):
        r=result(percent=80);r['calls'][0]['args']['x']=123
        with self.assertRaises(ValueError):validate_calls(r,CATALOG)
        r=result();r['calls']=[]
        with self.assertRaises(ValueError):validate_calls(r,CATALOG)
    def test_clarification_has_no_action(self):
        for status in ['clarify','reject']:
            validate_calls(dict(status=status,calls=[],message='Need a specific value'),CATALOG)
            r=result();r['status']=status
            with self.assertRaises(ValueError):validate_calls(r,CATALOG)
    def test_source_capability_limits(self):
        cat=copy.deepcopy(CATALOG);cat[0]['skills']=['SetBrightness']
        with self.assertRaises(ValueError):validate_calls(result('SetPower',state='on'),cat)
    def test_catalog_boundary(self):
        for cat in [[],CATALOG*2,[dict(device='bedroom_ac',skills=['SetTemperature'],values=[28])]]:
            with self.assertRaises(ValueError):validate_catalog(cat)

if __name__=='__main__':unittest.main()
