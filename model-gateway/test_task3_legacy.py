"""Old-file regression helpers; mocks are not device regression scores."""
import copy
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
import task3_legacy as legacy
from test_task3_audit import complete


def tree(file=None):
    ui=ET.Element('hierarchy')
    if file:ET.SubElement(ui,'node',{'resource-id':'android:id/title','text':file})
    return ui


class LegacyTests(unittest.TestCase):
    def test_already_visible_file_does_not_navigate_elsewhere(self):
        file='original.json';clicked=[]
        with patch.object(legacy.device,'tree',return_value=tree(file)),patch.object(legacy,'visible_click',side_effect=clicked.append):
            legacy.choose_download(file)
        self.assertEqual(len(clicked),1)
        self.assertTrue(clicked[0](tree(file)[0]))
        self.assertFalse(clicked[0](tree('other.json')[0]))

    def test_missing_file_only_opens_roots_and_downloads_then_stops(self):
        clicked=[]
        with patch.object(legacy.device,'tree',return_value=tree()),patch.object(legacy,'visible_click',side_effect=clicked.append),patch.object(legacy.time,'monotonic',side_effect=[0,0,7]),patch.object(legacy.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'PUBLIC_FILE_NOT_VISIBLE'):legacy.choose_download('missing.json')
        self.assertEqual(len(clicked),2)
        self.assertTrue(clicked[0](ET.Element('node',{'content-desc':'Show roots'})))
        self.assertTrue(clicked[1](ET.Element('node',{'resource-id':'android:id/title','text':'Downloads'})))

    def test_old_proof_requires_fresh_audits_and_identical_terminal(self):
        data=complete();skill,initial,result,oracle,journal,samples,disk,case_id=data
        self.assertTrue(legacy.identity_proof(skill,result,oracle,journal,samples))
        for kind in ['audits','terminal','run','sequence']:
            r,o,j,s=copy.deepcopy((result,oracle,journal,samples))
            if kind=='audits':s=s[:2]
            elif kind=='terminal':j[-1]['data']['reason']='rewritten'
            elif kind=='run':j[0]['runId']='another-run'
            else:j[0]['seq']=True
            with self.subTest(kind=kind):self.assertFalse(legacy.identity_proof(skill,r,o,j,s))


if __name__=='__main__':unittest.main()
