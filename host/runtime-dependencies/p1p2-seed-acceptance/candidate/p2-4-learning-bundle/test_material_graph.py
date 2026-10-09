import unittest
from test_support import bundle_fixture
from material_graph import search_known_route as public_search,_search_graph
from bundle_contract import BundleError

def search_known_route(bundle,source,target,*,validated_input=False):
    # Unit DTOs exercise only the algorithm, not evidence authenticity/Android completion.
    return _search_graph(bundle,source,target) if validated_input else public_search(bundle,source,target)

class GraphTests(unittest.TestCase):
    def graph(self):
        b=bundle_fixture();a=b['pages'][0]
        import copy
        for pid in ['page.b','page.c']:
            p=copy.deepcopy(a);p['page_id']=pid;b['pages'].append(p)
        # Explicit records only. Fixtures are graph DTOs, not proof of real Android edges.
        b['navigation']=[{'from_page':'page.a','to_page':'page.b','status':'VERIFIED_REAL_SCOPED','interaction_id':'step.ab'},
                         {'from_page':'page.b','to_page':'page.c','status':'VERIFIED_REAL_SCOPED','interaction_id':'step.bc'},
                         {'from_page':'page.b','to_page':'page.a','status':'VERIFIED_REAL_SCOPED','interaction_id':'step.ba'}]
        return b
    def test_two_steps(self):self.assertEqual(2,len(search_known_route(self.graph(),'page.a','page.c',validated_input=True)['edges']))
    def test_no_inverse(self):self.assertEqual('NO_KNOWN_PATH',search_known_route(self.graph(),'page.c','page.a',validated_input=True)['status'])
    def test_loop_terminates(self):self.assertEqual('NO_KNOWN_PATH',search_known_route(self.graph(),'page.a','page.missing',validated_input=True)['status'])
    def test_already(self):self.assertEqual('ALREADY_AT_TARGET',search_known_route(self.graph(),'page.a','page.a',validated_input=True)['status'])
    def test_hypothesis(self):
        b=self.graph();b['navigation'][0]['status']='HYPOTHESIS';self.assertEqual('NO_KNOWN_PATH',search_known_route(b,'page.a','page.c',validated_input=True)['status'])
    def test_invalidated(self):
        b=self.graph();b['navigation'][1]['status']='INVALIDATED';self.assertEqual('NO_KNOWN_PATH',search_known_route(b,'page.a','page.c',validated_input=True)['status'])
    def test_simulated_not_real(self):
        b=self.graph();b['navigation'][0]['status']='VERIFIED_SIMULATED';self.assertEqual('NO_KNOWN_PATH',search_known_route(b,'page.a','page.c',validated_input=True)['status'])
    def test_no_authority(self):self.assertFalse(search_known_route(self.graph(),'page.a','page.c',validated_input=True)['execution_authority'])
    def test_default_validation(self):
        with self.assertRaises(BundleError):search_known_route(self.graph(),'page.a','page.c')

if __name__=='__main__':unittest.main()
