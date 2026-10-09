import copy
import unittest
from skill_selection import build_request, validate_selection, select_skill, validate_catalog

CATALOG=[dict(id='a'*64,name='阅读60',goal='Read at 60%',finalGoals=[1,60,1,1]),
         dict(id='b'*64,name='明亮80',goal='Bright at 80%',finalGoals=[1,80,1,3])]

class SelectionTests(unittest.TestCase):
    def test_schema_only_allows_registered_ids_and_null(self):
        r=build_request('请执行阅读60',CATALOG)
        self.assertFalse(r['store'])
        self.assertEqual(r['text']['format']['schema']['properties']['skill_id']['enum'],['a'*64,'b'*64,None])
    def test_positive_and_refusal(self):
        for status,identity in [('invoke','a'*64),('clarify',None),('reject',None)]:
            x=dict(status=status,skill_id=identity,message='review first')
            self.assertEqual(validate_selection(x,CATALOG),x)
    def test_unknown_id_and_extra_actions_rejected(self):
        for x in [dict(status='invoke',skill_id='c'*64,message=''),dict(status='reject',skill_id='a'*64,message=''),
                  dict(status='invoke',skill_id=None,message=''),dict(status='invoke',skill_id='a'*64,message='',actions=[])]:
            with self.assertRaises(ValueError):validate_selection(x,CATALOG)
    def test_catalog_duplicates_invalid_goals_and_unknown_fields(self):
        variants=[[],CATALOG*2]
        for key,value in [('id','x'),('finalGoals',[True,60,1,1]),('finalGoals',[1,61,1,1]),('name','')]:
            data=copy.deepcopy(CATALOG);data[0][key]=value;variants.append(data)
        data=copy.deepcopy(CATALOG);data[0]['approved']=True;variants.append(data)
        for data in variants:
            with self.assertRaises(ValueError):validate_catalog(data)
    def test_invalid_text_no_call(self):
        for text in ['',None,'x'*501]:
            with self.assertRaises(ValueError):select_skill(text,CATALOG,lambda r:self.fail('remote invoked'))
    def test_validates_transport_output(self):
        with self.assertRaises(ValueError):select_skill('read',CATALOG,lambda r:dict(draft=dict(status='invoke',skill_id='wrong',message='')))

if __name__=='__main__':unittest.main()
