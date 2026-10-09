import copy
import unittest
from catalog_uniqueness import guard_selection
from test_skill_selection import CATALOG


class CatalogUniquenessTests(unittest.TestCase):
    def setUp(self):
        self.skills=copy.deepcopy(CATALOG)
        self.skills[0]['name']='阅读60 / Reading60'
        self.skills.append(dict(id='c'*64,name='阅读60备份 / Reading60 Copy',goal='same goals',finalGoals=self.skills[0]['finalGoals'][:]))
        self.proposal=dict(status='invoke',skill_id='a'*64,message='Review')

    def test_high_confidence_cannot_override_goal_ambiguity(self):
        out=guard_selection('Turn on lamp at 60% and fan at low speed.',self.skills,self.proposal)
        self.assertEqual(out['status'],'clarify'); self.assertIsNone(out['skill_id'])
        self.assertEqual(self.proposal['status'],'invoke')

    def test_plain_explicit_bilingual_name_still_works(self):
        for command in ['Run Reading60.','Please run my saved "Reading60" workflow.','执行阅读60。','请运行我保存的“阅读60 / Reading60”技能。']:
            self.assertEqual(guard_selection(command,self.skills,self.proposal)['skill_id'],'a'*64)

    def test_negated_quoted_modified_and_complex_names_do_not_bypass(self):
        for command in ['Do not run Reading60.','Run Reading60 but turn fan off.','Run Reading60 Copy.',
                        'Yesterday I said "run Reading60".','不要执行阅读60。','执行阅读60然后别的技能',
                        'Run the original Reading60, not Reading60 Copy.']:
            self.assertEqual(guard_selection(command,self.skills,self.proposal)['status'],'clarify')

    def test_ambiguous_alias_and_unregistered_id_are_not_accepted(self):
        self.skills[-1]['name']='另一个 / Reading60'
        self.assertEqual(guard_selection('Run Reading60.',self.skills,self.proposal)['status'],'clarify')
        bad=dict(self.proposal,skill_id='f'*64)
        with self.assertRaises(ValueError): guard_selection('Run Reading60.',self.skills,bad)

    def test_unique_goal_and_noninvoke_leave_original_proposal_unchanged(self):
        self.assertEqual(guard_selection('unrestricted model-understood text',CATALOG,self.proposal),self.proposal)
        non=dict(status='reject',skill_id=None,message='No')
        self.assertEqual(guard_selection('Run Reading60.',self.skills,non),non)


if __name__=='__main__': unittest.main()
