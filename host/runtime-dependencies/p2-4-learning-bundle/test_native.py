import copy
import unittest
from bundle_contract import BundleError
from test_support import ENV
from native_materials import validate_native_observation,derive_native_page,native_bundle,validate_native_interaction

def obs_fixture(marker='lamp | bedroom',value=60,obsid='a'*32):
    from observation_tree import FIELDS
    nodes=[]
    for i,(rid,text,role) in enumerate([('root',None,'container'),('wfPage',marker,'text'),('wfReady','Ready','text'),('wfOverallDirty','Saved','text'),('head','Reading lamp','text'),('wfLampPower','ON','switch'),('wfLampValue','60','radio'),('wfLampBack','返回 Back','button')]):
        row={k:None for k in FIELDS};row.update(node_local_id='n'+str(i),parent_local_id=None if i==0 else 'n0',package='edu.sydney.transferlab',resource_id='edu.sydney.transferlab:id/'+rid,class_name='android.widget.LinearLayout' if i==0 else 'android.widget.Button' if role=='button' else 'android.widget.TextView',role=role,text=text,content_description=None,bounds=[0,0,100,20],visible=True,enabled=True,clickable=role in ['button','switch','radio'],checkable=role in ['switch','radio'],checked=role=='switch',selected=False,editable=False,password=False,heading=False)
        if rid=='wfLampValue':row['range']={'min':20,'max':100,'value':value,'kind':'int'}
        nodes.append(row)
    tree={'nodes':nodes,'root_readable':True,'complete':True,'truncated_reasons':[]}
    snapshot={'window_id':7,'display_id':0,'tree':tree}
    return {'kind':'NativePageObservation','schema_version':'1.0','observation_id':obsid,'channel':'REAL_ANDROID_BOUND_SERVICE','process_session':'boot.session.a',
            'scope_id':'c'*32,'app_package':'edu.sydney.transferlab','app_build':6,'captured_elapsed_ms':100,'captured_uptime_ms':100,'capture_started_elapsed_ms':90,
            'window_id':7,'display_id':0,'tree':tree,'device_context':{'status':'AVAILABLE','snapshot':{'deviceId':'public-host.a'}},
            'attempts':[{'attempt_id':obsid+':1','tree_a_start_uptime_ms':90,'tree_a_end_uptime_ms':95,'tree_b_start_uptime_ms':95,'tree_b_end_uptime_ms':100,'tree_a':snapshot,'tree_b':copy.deepcopy(snapshot),'status':'VALID_TREE_ONLY'}],
            'status':'VALID_TREE_ONLY','screenshot':None,'screenshot_status':'NOT_REQUESTED','pairing_level':'WINDOW_TIME_CHECKED','visual_content_check':'NOT_EVALUATED','limitations':['NOT_ATOMIC_FRAME','NO_VISUAL_CONTENT_CHECK']}

NENV={**ENV,'app_package':'edu.sydney.transferlab','app_build':'6'}
class NativeTests(unittest.TestCase):
    def test_real_channel(self):self.assertEqual('REAL_ANDROID_BOUND_SERVICE',validate_native_observation(obs_fixture())['channel'])
    def test_wrong_channel(self):
        o=obs_fixture();o['channel']='OFFLINE_CALLBACK_SIMULATION'
        with self.assertRaises(BundleError):validate_native_observation(o)
    def test_unpaired_tree(self):
        o=obs_fixture();o['attempts'][0]['tree_a']['tree']=copy.deepcopy(o['tree']);o['attempts'][0]['tree_a']['tree']['nodes'][1]['text']='fan | bedroom'
        with self.assertRaises(BundleError):validate_native_observation(o)
    def test_wrong_window(self):
        o=obs_fixture();o['attempts'][0]['tree_b']['window_id']=8
        with self.assertRaises(BundleError):validate_native_observation(o)
    def test_pair_expired(self):
        o=obs_fixture();o['attempts'][0]['tree_a_start_uptime_ms']=0;o['attempts'][0]['tree_b_end_uptime_ms']=251
        with self.assertRaises(BundleError):validate_native_observation(o)
    def test_wrong_clock(self):
        o=obs_fixture();o['attempts'][0]['tree_a_end_uptime_ms']=80
        with self.assertRaises(BundleError):validate_native_observation(o)
    def test_total_budget(self):
        o=obs_fixture();o['captured_elapsed_ms']=3000
        with self.assertRaises(BundleError):validate_native_observation(o)
    def test_old_screenshot(self):
        o=obs_fixture();o['screenshot']={'id':'old'}
        with self.assertRaises(BundleError):validate_native_observation(o)
    def test_old_node_object(self):
        o=obs_fixture();o['tree']['nodes'][0]['binder']=object()
        with self.assertRaises(BundleError):validate_native_observation(o)
    def test_duplicate_id(self):
        o=obs_fixture();o['tree']['nodes'][1]['node_local_id']='n0'
        with self.assertRaises(BundleError):validate_native_observation(o)
    def test_missing_parent(self):
        o=obs_fixture();o['tree']['nodes'][1]['parent_local_id']='missing'
        with self.assertRaises(BundleError):validate_native_observation(o)
    def test_same_page_dynamic_values(self):
        a=derive_native_page(obs_fixture(value=60),NENV,'source.a');b=derive_native_page(obs_fixture(value=80,obsid='b'*32),NENV,'source.b');self.assertEqual(a['page_id'],b['page_id'])
    def test_different_room(self):
        a=derive_native_page(obs_fixture('lamp | Room 101'),NENV,'source.a');b=derive_native_page(obs_fixture('lamp | Room 102'),NENV,'source.b');self.assertNotEqual(a['page_id'],b['page_id']);self.assertEqual(a['template_id'],b['template_id'])
    def test_unknown_not_merged(self):
        a=derive_native_page(obs_fixture('Unknown'),NENV,'source.a');b=derive_native_page(obs_fixture('Unknown',obsid='b'*32),NENV,'source.b');self.assertNotEqual(a['page_id'],b['page_id']);self.assertEqual('UNKNOWN',a['identity_status'])
    def test_conflicting_marker(self):
        o=obs_fixture();n=copy.deepcopy(o['tree']['nodes'][1]);n['node_local_id']='n99';n['text']='fan | bedroom';o['tree']['nodes'].append(n)
        o['attempts'][0]['tree_b']['tree']=copy.deepcopy(o['tree'])
        a=derive_native_page(o,NENV,'source.a');self.assertEqual('AMBIGUOUS',a['identity_status'])
    def test_bundle_no_laundering(self):
        b=native_bundle([obs_fixture()],[],NENV);self.assertEqual('REAL_ANDROID_BOUND_SERVICE',b['sources'][0]['channel']);self.assertFalse(b['execution_authority']);self.assertNotIn('scope_id',b['sources'][0]['fragment'])
    def test_wrong_environment(self):
        with self.assertRaises(BundleError):native_bundle([obs_fixture()],[],{**NENV,'app_build':'7'})
    def test_missing_context(self):
        o=obs_fixture();o['device_context']['snapshot']=None
        with self.assertRaises(BundleError):validate_native_observation(o)
    def test_hypothesis_not_real_nav(self):
        with self.assertRaises(BundleError):validate_native_interaction({'actor':'MODEL','status':'SUCCESS'})
    def test_actor_unknown_on_passive_event(self):
        b=native_bundle([obs_fixture()],[],NENV);self.assertEqual([],b['interactions'])
    def test_clipped_hidden_geometry_is_unknown_not_fabricated(self):
        o=obs_fixture();o['tree']['nodes'][7]['visible']=False;o['tree']['nodes'][7]['bounds']=[10,100,30,80]
        o['attempts'][0]['tree_b']['tree']=copy.deepcopy(o['tree'])
        p=derive_native_page(o,NENV,'source.a')
        self.assertIsNone(p['elements'][7]['bounds'])
        self.assertFalse(p['elements'][7]['visible'])
        self.assertIn('CLIPPED_GEOMETRY_UNAVAILABLE',p['limitations'])
        self.assertEqual([10,100,30,80],o['tree']['nodes'][7]['bounds'])
    def test_invalid_visible_geometry_is_rejected(self):
        o=obs_fixture();o['tree']['nodes'][7]['bounds']=[10,100,30,80]
        o['attempts'][0]['tree_b']['tree']=copy.deepcopy(o['tree'])
        with self.assertRaises(BundleError):validate_native_observation(o)

if __name__=='__main__':unittest.main()
