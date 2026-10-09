import unittest
from skill_selection import validate_catalog
from catalog_uniqueness import guard_selection

class FlexibleSelectionTests(unittest.TestCase):
    def catalog(self):
        return [dict(id='a'*64,name='只调亮度 / BrightnessOnly',goal='Set brightness to 60%; keep power and fan unchanged.',finalGoals=[None,60,None,None],processMode='ORDERED')]
    def invoke(self):return dict(status='invoke',skill_id='a'*64,message='Preview only')
    def test_partial_field_catalog(self):validate_catalog(self.catalog())
    def test_named_ordered_skill_can_be_selected(self):
        for text in ['执行只调亮度','Run BrightnessOnly']:
            self.assertEqual(guard_selection(text,self.catalog(),self.invoke())['status'],'invoke')
    def test_final_goals_do_not_authorize_an_ordered_process(self):
        self.assertEqual(guard_selection('Set brightness to sixty percent',self.catalog(),self.invoke())['status'],'clarify')
    def test_negation_and_parameter_change_do_not_authorize(self):
        for text in ['不要执行只调亮度','Run BrightnessOnly but set it to 80%']:
            self.assertEqual(guard_selection(text,self.catalog(),self.invoke())['status'],'clarify')
    def test_legacy_scope_unchanged_and_bad_mode_rejected(self):
        for mode in [None,'UNBOUNDED']:
            s=self.catalog()[0]
            if mode is None:s.pop('processMode')
            else:s['processMode']=mode
            with self.assertRaises(ValueError):validate_catalog([s])

if __name__=='__main__':unittest.main()
