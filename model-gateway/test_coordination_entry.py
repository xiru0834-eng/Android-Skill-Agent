import unittest
from start_teaching_bridge import resolve_selector
from test_skill_selection import CATALOG
from test_jev_selection import response


class CoordinationEntryTests(unittest.TestCase):
    def test_product_route_uses_full_rubric_for_nonliteral_input(self):
        calls=[]
        def transport(body):calls.append(body);return response('clarify')
        selected=resolve_selector('routed')('Please use the saved reading workflow.',CATALOG,transport=transport)
        self.assertEqual(selected['status'],'clarify')
        self.assertEqual(calls[0]['state']['skills'],CATALOG)

    def test_product_route_literal_name_has_no_api(self):
        selected=resolve_selector('routed')('执行阅读60',CATALOG,transport=lambda _:self.fail('API called'))
        self.assertEqual(selected['skill_id'],'a'*64)

    def test_existing_modes_keep_their_functions_and_unknown_mode_fails(self):
        from skill_selection import select_skill
        from jev_selection import select_jev
        self.assertIs(resolve_selector('gpt'),select_skill)
        self.assertIs(resolve_selector('jev'),select_jev)
        with self.assertRaises(ValueError):resolve_selector('unknown')


if __name__=='__main__':unittest.main()
