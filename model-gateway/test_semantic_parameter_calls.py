import copy
import json
import unittest
from semantic_parameter_calls import build_request, validate_calls, validate_catalog, catalog_hash


def entity(device, skill, values, name=None):
    return dict(device=device, name=name or device, aliases=[],
                capabilities=[dict(skill=skill, domain=dict(values=values))])


CATALOG = [
    entity('reading_lamp', 'SetPower', ['on', 'off'], '阅读灯'),
    entity('desk_lamp', 'SetBrightness', [0, 20, 40, 60, 80, 100]),
    entity('bedroom_ac', 'SetTemperature', [16, 20, 24, 28, 30]),
    entity('desk_fan', 'SetFanSpeed', [1, 2, 3]),
    entity('window_curtain', 'SetCurtain', [0, 20, 40, 60, 80, 100]),
    entity('air_conditioner', 'SetMode', ['cool', 'heat', 'auto']),
    entity('humidifier', 'SetTargetHumidity', [40, 50, 60]),
    entity('ceiling_lamp', 'SetColorTemperature', [2700, 4000, 6500]),
]


def invocation(skill='SetBrightness', device='desk_lamp', **args):
    return dict(status='invoke', calls=[dict(skill=skill, args=dict(device=device, **(args or dict(percent=80))))], message='Review')


class SemanticParameterTests(unittest.TestCase):
    def test_eight_actions_dynamic_entities(self):
        args = [('SetPower','state','on'), ('SetBrightness','percent',80),
                ('SetTemperature','celsius',24), ('SetFanSpeed','level',2),
                ('SetCurtain','position',40), ('SetMode','mode','cool'),
                ('SetTargetHumidity','percent',50), ('SetColorTemperature','kelvin',4000)]
        for row, (skill, key, value) in zip(CATALOG, args):
            data=invocation(skill, row['device'], **{key:value})
            self.assertEqual(validate_calls(data,CATALOG),data)
        self.assertNotIn('bedroom_light', json.dumps(build_request('把阅读灯打开', CATALOG)))

    def test_same_skill_different_values_per_entity(self):
        catalog=[entity('a','SetBrightness',[20,40]),entity('b','SetBrightness',[60,80])]
        validate_calls(invocation(device='a',percent=20),catalog)
        with self.assertRaises(ValueError):validate_calls(invocation(device='a',percent=80),catalog)
        validate_calls(invocation(device='b',percent=80),catalog)

    def test_exact_integer_range_and_step(self):
        row=entity('a','SetTemperature',[24]);row['capabilities'][0]['domain']=dict(min=16,max=30,step=2)
        for value in [16,24,30]:validate_calls(invocation('SetTemperature','a',celsius=value),[row])
        for value in [15,17,31,True,24.0,'24',None]:
            with self.subTest(value=value),self.assertRaises(ValueError):validate_calls(invocation('SetTemperature','a',celsius=value),[row])

    def test_thirty_two_ordered_calls_keep_repeated_assignments(self):
        data=invocation();data['calls']=[invocation(percent=20 if i%2==0 else 100)['calls'][0] for i in range(32)]
        original=copy.deepcopy(data);validate_calls(data,CATALOG);self.assertEqual(data,original)
        data['calls'].append(data['calls'][0])
        with self.assertRaises(ValueError):validate_calls(data,CATALOG)

    def test_whole_list_rejected_when_last_call_invalid(self):
        data=invocation();data['calls']*=8;data['calls'].append(invocation(device='ghost')['calls'][0])
        original=copy.deepcopy(data)
        with self.assertRaises(ValueError):validate_calls(data,CATALOG)
        self.assertEqual(data,original)

    def test_no_coercion_or_extra_fields(self):
        for value in [True,80.0,'80',None,-1,101]:
            with self.subTest(value=value),self.assertRaises(ValueError):validate_calls(invocation(percent=value),CATALOG)
        data=invocation();data['calls'][0]['args']['x']=12
        with self.assertRaises(ValueError):validate_calls(data,CATALOG)
        data=invocation();data['calls'][0]['skill']='ExecuteCode'
        with self.assertRaises(ValueError):validate_calls(data,CATALOG)

    def test_noninvoke_empty_and_known_status(self):
        for status in ['clarify','reject']:
            validate_calls(dict(status=status,calls=[],message='Please clarify'),CATALOG)
            data=invocation();data['status']=status
            with self.assertRaises(ValueError):validate_calls(data,CATALOG)
        for status in [None,True,'approved']:
            data=invocation();data['status']=status
            with self.assertRaises(ValueError):validate_calls(data,CATALOG)

    def test_catalog_limits_duplicates_and_untrusted_binding_fields(self):
        validate_catalog([entity('lamp_'+str(i),'SetPower',['on','off']) for i in range(128)])
        invalid=[[],CATALOG+[CATALOG[0]],[entity('lamp_'+str(i),'SetPower',['on','off']) for i in range(129)]]
        for key,value in [('x',12),('resource_id','someId'),('approved',True)]:
            row=copy.deepcopy(CATALOG[0]);row[key]=value;invalid.append([row])
        for catalog in invalid:
            with self.assertRaises(ValueError):validate_catalog(catalog)

    def test_invalid_domain_and_capability(self):
        for domain in [dict(values=[]),dict(values=[80,80]),dict(values=[True]),dict(values=[101]),
                       dict(min=0,max=100,step=0),dict(min=100,max=0,step=1),
                       dict(min=0,max=100,step=True),dict(values=[80],min=0)]:
            row=copy.deepcopy(CATALOG[1]);row['capabilities'][0]['domain']=domain
            with self.subTest(domain=domain),self.assertRaises(ValueError):validate_catalog([row])
        row=copy.deepcopy(CATALOG[0]);row['capabilities']*=2
        with self.assertRaises(ValueError):validate_catalog([row])

    def test_domain_and_mode_match_android_semantic_contract(self):
        row=entity('a','SetTemperature',[24]);row['capabilities'][0]['domain']=dict(min=16,max=30,step=3)
        with self.assertRaises(ValueError):validate_catalog([row])
        row=entity('a','SetMode',['a'*33])
        with self.assertRaises(ValueError):validate_catalog([row])
        row=entity('a','SetFanSpeed',list(range(1,257)))
        validate_catalog([row])
        row=entity('a','SetPower',['on','off']);row['name']='lamp\x7f'
        with self.assertRaises(ValueError):validate_catalog([row])

    def test_text_and_immutable_request_snapshot(self):
        for text in ['', ' '*5, 'a'*2001,'bad\ncommand','\ud800']:
            with self.assertRaises(ValueError):build_request(text,CATALOG)
        cat=copy.deepcopy(CATALOG);request=build_request('Set brightness to eighty percent.',cat)
        before=json.dumps(request);cat[1]['capabilities'][0]['domain']['values'].clear()
        self.assertEqual(json.dumps(request),before)
        self.assertEqual(request['max_output_tokens'],4096)

    def test_hash_changes_only_with_content_and_schema_has_no_coordinates(self):
        reordered=json.loads(json.dumps(CATALOG,sort_keys=True))
        self.assertEqual(catalog_hash(CATALOG),catalog_hash(reordered))
        changed=copy.deepcopy(CATALOG);changed[0]['name']='Light A'
        self.assertNotEqual(catalog_hash(CATALOG),catalog_hash(changed))
        request=build_request('Set the curtain to 60 percent',CATALOG)
        self.assertTrue(request['text']['format']['strict'])
        self.assertFalse(request['store'])
        self.assertEqual(len(request['text']['format']['schema']['properties']['calls']['items']['anyOf']),8)
        self.assertNotIn('resource_id',str(request))

    def test_catalog_byte_limit_uses_same_compact_form_as_android(self):
        # Whitespace in a Python serializer is not part of the native catalog
        # size. Otherwise a valid native snapshot can fail before any model call.
        catalog=[]
        for i in range(128):
            catalog.append(entity('lamp_'+str(i),'SetPower',['on','off'],name='L'*80))
            compact=len(json.dumps(catalog,ensure_ascii=False,separators=(',',':')).encode())
            spaced=len(json.dumps(catalog,ensure_ascii=False).encode())
            if compact<=24000<spaced:break
        self.assertLessEqual(compact,24000)
        self.assertGreater(spaced,24000)
        validate_catalog(catalog)
        while len(json.dumps(catalog,ensure_ascii=False,separators=(',',':')).encode())<=24000:
            catalog.append(entity('extra_'+str(len(catalog)),'SetPower',['on','off'],name='L'*80))
        self.assertLessEqual(len(catalog),128)
        with self.assertRaises(ValueError):validate_catalog(catalog)


if __name__=='__main__':unittest.main()
