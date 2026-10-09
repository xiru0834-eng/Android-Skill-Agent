import unittest
from compiler import ModelError
from jev_selection import MODEL
from selection_accuracy import select_accuracy

CATALOG=[dict(id='a'*64,name='阅读60 / Reading60',goal='Both devices.',finalGoals=[1,60,1,1]),
         dict(id='b'*64,name='只灯60 / LampOnly60',goal='Lamp only.',finalGoals=[1,60,None,None])]


def response(choice='skill_1',confidence=.88,prob=.92):
    options=['skill_0','skill_1','clarify','reject']
    return dict(model=MODEL,answers=dict(selection=dict(type='choice',choice=choice,confidence=confidence,
        probabilities={k:prob if k==choice else (1-prob)/3 for k in options})))


class SelectionAccuracyTests(unittest.TestCase):
    def test_missing_saved_identity_never_calls_model(self):
        for text in ['我想运行保存的陌生90，而不是替换成其他模式。','Use the saved Missing90 workflow now.']:
            got=select_accuracy(text,CATALOG,lambda _:self.fail('Jev called'),lambda _:self.fail('GPT called'),review=True)
            self.assertEqual(got['status'],'reject');self.assertIsNone(got['skill_id'])

    def test_named_identity_cannot_be_replaced_by_another_reviewed_id(self):
        got=select_accuracy('Use the saved Reading60 workflow now.',CATALOG,
            lambda _:response(confidence=.99,prob=.99),lambda _:self.fail('GPT called'),review=True)
        self.assertEqual(got['status'],'clarify')

    def test_low_positive_candidate_gets_at_most_one_gpt_review(self):
        calls=[]
        def gpt(_):calls.append(1);return dict(draft=dict(status='invoke',skill_id='b'*64,message='review'))
        got=select_accuracy('Use the workflow called LampOnly60 with its saved settings.',CATALOG,
            lambda _:response(),gpt,review=True)
        self.assertEqual(got['skill_id'],'b'*64);self.assertEqual(calls,[1])

    def test_ablation_preserves_abstention_without_second_model(self):
        got=select_accuracy('Please use my lamp routine.',CATALOG,lambda _:response(),
            lambda _:self.fail('GPT called'),review=False)
        self.assertEqual(got['status'],'clarify')

    def test_reject_or_explicit_clarify_never_triggers_gpt(self):
        for choice in ['reject','clarify']:
            got=select_accuracy('Do not perform any operation.',CATALOG,
                lambda _:response(choice=choice,confidence=.99,prob=.99),lambda _:self.fail('GPT called'),review=True)
            self.assertEqual(got['status'],choice)

    def test_network_error_never_unlocks_second_model(self):
        def fail(_):raise ModelError('NETWORK_OR_TIMEOUT')
        with self.assertRaises(ModelError):select_accuracy('I want lamp ON at sixty percent with the fan unchanged.',CATALOG,
            fail,lambda _:self.fail('GPT called'),review=True)

    def test_literal_name_and_high_confidence_do_not_add_review(self):
        got=select_accuracy('Run Reading60.',CATALOG,lambda _:self.fail('Jev called'),
            lambda _:self.fail('GPT called'),review=True)
        self.assertEqual(got['skill_id'],'a'*64)
        got=select_accuracy('Only the lamp ON at sixty percent.',CATALOG,
            lambda _:response(confidence=.99,prob=.99),lambda _:self.fail('GPT called'),review=True)
        self.assertEqual(got['skill_id'],'b'*64)

    def test_structural_equivalent_goal_ambiguity_is_not_reviewed(self):
        items=CATALOG+[dict(id='c'*64,name='Copy',goal='Same.',finalGoals=[1,60,1,1])]
        options=['skill_0','skill_1','skill_2','clarify','reject']
        raw=dict(model=MODEL,answers=dict(selection=dict(type='choice',choice='skill_0',confidence=.88,
            probabilities={k:.92 if k=='skill_0' else .02 for k in options})))
        got=select_accuracy('Both ON, lamp sixty percent and fan low.',items,lambda _:raw,
            lambda _:self.fail('GPT called'),review=True)
        self.assertEqual(got['status'],'clarify')

    def test_second_model_denial_and_mismatched_identity_remain_safe(self):
        got=select_accuracy('I only need an explanation.',CATALOG,lambda _:response(),
            lambda _:dict(draft=dict(status='reject',skill_id=None,message='no')),review=True)
        self.assertEqual(got['status'],'reject')
        got=select_accuracy('Use the saved LampOnly60 workflow now.',CATALOG,lambda _:response(),
            lambda _:dict(draft=dict(status='invoke',skill_id='a'*64,message='wrong')),review=True)
        self.assertEqual(got['status'],'clarify')


if __name__=='__main__':unittest.main()
