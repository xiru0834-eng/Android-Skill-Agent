import copy
import unittest
from test_skill_selection import CATALOG
from jev_selection import build_request,parse_selection,select_jev,MODEL

def response(choice='skill_0',probability=.96,confidence=.97):
    options=['skill_0','skill_1','clarify','reject']
    probs={k:(1-probability)/(len(options)-1) for k in options};probs[choice]=probability
    return dict(model=MODEL,answers=dict(selection=dict(type='choice',choice=choice,probabilities=probs,confidence=confidence)),usage=dict(input_tokens=100,output_tokens=20))

class JevSelectionTests(unittest.TestCase):
    def test_same_catalog_policy_and_immutable_id(self):
        body=build_request('执行阅读60',CATALOG)
        self.assertEqual(body['model'],MODEL)
        self.assertEqual(body['state']['skills'],CATALOG)
        self.assertEqual(set(body['questions']['selection']['criteria']),{'skill_0','skill_1','clarify','reject'})
        self.assertEqual(parse_selection(response(),CATALOG)['skill_id'],'a'*64)
    def test_non_invokes_keep_null_and_low_confidence_abstains(self):
        for choice in ['clarify','reject']:
            data=parse_selection(response(choice),CATALOG)
            self.assertEqual(data['status'],choice);self.assertIsNone(data['skill_id'])
        for p,c in [(.89,.99),(.99,.89)]:
            data=parse_selection(response(probability=p,confidence=c),CATALOG)
            self.assertEqual(data['status'],'clarify');self.assertIsNone(data['skill_id'])
    def test_response_boundaries_fail_closed(self):
        variants=[]
        x=response();x['model']='jev-latest';variants.append(x)
        for field,value in [('choice','unregistered'),('confidence',True),('confidence',float('nan')),('type','noul'),('probabilities',{'skill_0':1})]:
            x=response();x['answers']['selection'][field]=value;variants.append(x)
        x=response();x['answers']['selection']['probabilities']['skill_1']=2;variants.append(x)
        x=response();x['answers']['selection']['choice']='skill_1';variants.append(x)
        x=response();x['answers']['extra']={};variants.append(x)
        for x in variants:
            with self.assertRaises(ValueError):parse_selection(x,CATALOG)
    def test_invalid_input_does_not_call(self):
        for text in ['',None,'x'*501]:
            with self.assertRaises(ValueError):select_jev(text,CATALOG,lambda body:self.fail('remote invoked'))
    def test_adapter_returns_existing_contract_only(self):
        data=select_jev('read',CATALOG,lambda body:response())
        self.assertEqual(set(data),{'status','skill_id','message'})
        self.assertEqual(CATALOG[0]['finalGoals'],[1,60,1,1])
    def test_adapter_applies_catalog_uniqueness_before_preview(self):
        skills=copy.deepcopy(CATALOG)
        skills.append(dict(skills[0],id='c'*64,name='Another route'))
        data=response()
        data['answers']['selection']['probabilities']['skill_2']=0
        result=select_jev('Set lamp and fan to the target.',skills,lambda _:data)
        self.assertEqual(result['status'],'clarify');self.assertIsNone(result['skill_id'])

if __name__=='__main__':unittest.main()
