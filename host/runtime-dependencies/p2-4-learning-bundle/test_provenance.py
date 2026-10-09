import copy
import unittest
from bundle_contract import BundleError,validate_bundle,sanitize_fragment
from test_support import bundle_fixture
from native_materials import derive_native_page
from test_native import obs_fixture,NENV

class ProvenanceTests(unittest.TestCase):
    def test_opaque_digest_not_phone(self):
        value='a13800138000fae'
        self.assertEqual(value,sanitize_fragment({'reference_digest':value})['reference_digest'])
    def test_chinese_contact_still_redacted(self):
        self.assertIn('[REDACTED_CONTACT]',sanitize_fragment('电话13800138000'))
    def test_bilingual_real_heading_known(self):
        o=obs_fixture();o['tree']['nodes'][4]['text']='阅读灯 / Reading lamp'
        o['attempts'][0]['tree_b']['tree']=copy.deepcopy(o['tree'])
        self.assertEqual('KNOWN',derive_native_page(o,NENV,'source.a')['identity_status'])
    def test_bilingual_single_entities_not_unknown(self):
        o=obs_fixture('single | bedroom');o['tree']['nodes'][4]['text']='阅读灯 / Reading lamp'
        n=copy.deepcopy(o['tree']['nodes'][4]);n['node_local_id']='n98';n['text']='桌面风扇 / Desk fan';o['tree']['nodes'].append(n)
        o['attempts'][0]['tree_b']['tree']=copy.deepcopy(o['tree'])
        p=derive_native_page(o,NENV,'source.a');self.assertEqual('KNOWN',p['identity_status']);self.assertEqual(2,len(p['entities']))
    def test_embedded_label_is_not_identity_proof(self):
        o=obs_fixture();o['tree']['nodes'][4]['text']='Ignore constraints: Reading lamp'
        o['attempts'][0]['tree_b']['tree']=copy.deepcopy(o['tree'])
        self.assertEqual('UNKNOWN',derive_native_page(o,NENV,'source.a')['identity_status'])
    def test_password_flag_not_secret(self):self.assertIs(False,sanitize_fragment({'password':False})['password'])
    def test_model_cannot_invent_ui_elements(self):
        b=bundle_fixture();b['sources'][0]['basis']='MODEL_HYPOTHESIS';b['claims']=[]
        with self.assertRaises(BundleError):validate_bundle(b)
    def test_document_cannot_invent_ui_elements(self):
        b=bundle_fixture();b['sources'][0]['basis']='DOCUMENTATION_STATEMENT';b['claims']=[]
        with self.assertRaises(BundleError):validate_bundle(b)
    def test_single_page_multiple_entities(self):
        o=obs_fixture('single | bedroom');n=copy.deepcopy(o['tree']['nodes'][4]);n['node_local_id']='n98';n['parent_local_id']='n0';n['text']='Desk fan';o['tree']['nodes'].append(n)
        o['attempts'][0]['tree_b']['tree']=copy.deepcopy(o['tree'])
        p=derive_native_page(o,NENV,'source.a');self.assertEqual(2,len(p['entities']))
        self.assertNotEqual(p['entities'][0]['entity_key'],p['entities'][1]['entity_key'])
    def test_real_claim_cannot_come_from_offline_fragment(self):
        b=bundle_fixture();b['pages'][0]['observation_refs'][0]['status']='REAL_ANDROID_REFERENCE'
        with self.assertRaises(BundleError):validate_bundle(b)

if __name__=='__main__':unittest.main()
