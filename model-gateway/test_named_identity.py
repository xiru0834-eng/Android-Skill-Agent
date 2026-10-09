import copy
import unittest
from catalog_uniqueness import guard_selection,explicit_name_id
from test_skill_selection import CATALOG

class NamedIdentityTests(unittest.TestCase):
    def setUp(self):
        self.skills=copy.deepcopy(CATALOG)
        self.skills[0]['name']='阅读60 / Reading60'
        self.skills.append(dict(id='c'*64,name='备份 / Copy60',goal='Same',finalGoals=[1,60,1,1]))
        self.proposal=dict(status='invoke',skill_id='a'*64,message='Review')

    def test_reproduce_model_correct_but_guard_rejected(self):
        for text in ['现在用名称为阅读60的那条已有技能，其他同目标的不选。',
                     'Use the existing workflow named Reading60 now, not another one with identical targets.']:
            self.assertEqual(guard_selection(text,self.skills,self.proposal),self.proposal)
            self.assertIsNone(explicit_name_id(text,self.skills))

    def test_supported_name_evidence_is_not_reading_specific(self):
        self.skills[0]['name']='雪松模式 / CedarMode'
        for text in ['Please use the saved workflow called "CedarMode", as saved.',
                     'Execute the existing skill named CedarMode now.',
                     '请使用名为“雪松模式”的已有流程，保持原样。',
                     '现在运行名称为雪松模式的已保存技能。']:
            self.assertEqual(guard_selection(text,self.skills,self.proposal),self.proposal)
            self.assertIsNone(explicit_name_id(text,self.skills))

    def test_no_identity_hint_overrides_semantic_denial_or_wrong_id(self):
        text='Use the existing workflow named Reading60 now.'
        for status in ['reject','clarify']:
            p=dict(status=status,skill_id=None,message='No')
            self.assertEqual(guard_selection(text,self.skills,p),p)
        wrong=dict(self.proposal,skill_id='c'*64)
        self.assertEqual(guard_selection(text,self.skills,wrong)['status'],'clarify')

    def test_bounded_evidence_rejects_unsafe_contexts_and_prefixes(self):
        for text in ['Use the existing workflow named Reading600 now.',
                     'Use the existing workflow named Reading60 Copy now.',
                     'Do not use the existing workflow named Reading60 now.',
                     'If I get home, use the existing workflow named Reading60 now.',
                     'Yesterday I said: use the existing workflow named Reading60 now.',
                     'Use the existing workflow named Reading60 now, but set brightness to 20%.',
                     'Use the existing workflow named Reading60 now, then run Copy60.',
                     '请不要使用名为阅读60的已有流程。',
                     '如果到家就使用名为阅读60的已有流程。',
                     '请使用名为阅读60的已有流程，亮度改为20%。',
                     '请使用名为阅读60的已有流程，然后执行备份。']:
            self.assertEqual(guard_selection(text,self.skills,self.proposal)['status'],'clarify',text)

    def test_alias_collision_does_not_bind(self):
        self.skills[-1]['name']='另一条 / Reading60'
        self.assertEqual(guard_selection('Use the existing workflow named Reading60 now.',self.skills,self.proposal)['status'],'clarify')

if __name__=='__main__':unittest.main()
