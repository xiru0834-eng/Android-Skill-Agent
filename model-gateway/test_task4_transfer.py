"""Transfer contract adversaries; synthetic evidence is not an Android trial."""
import copy
import json
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
from task4_protocol import source_record,canonical,display_state
from task4_transfer import chain_check,restore_commands,fault_trigger,fault_score
from task4_files import visible_node,wait_marker
from test_task3_workflows import sample


def chain():
    expected=source_record('S3')['package'];blob=canonical(expected).encode()
    before={'library':'[]','result':'old','draft':'old draft'}
    pending=dict(before,pendingNamed=json.dumps(expected))
    after=dict(before,library=json.dumps([expected]),approved=json.dumps(expected['skill']))
    return expected,dict(sourceAvd='Task3Workflows',targetAvd='Task4Transfer',sourceBlob=blob,targetBlob=blob,
        sourceBefore=before,sourceAfter=copy.deepcopy(before),before=before,pending=pending,after=after,
        exportXml='<node text="Skill exported. Approval, accounts and run history were not exported."/>',
        importXml='<node text="Import draft: T3 S3"/>',reviewXml='<node resource-id="android:id/button1" text="Save"/>')


class TransferTests(unittest.TestCase):
    def test_original_bytes_pending_and_local_review_chain(self):
        pack,proof=chain();self.assertTrue(chain_check(pack,proof)['correctChain'])
    def test_chain_rejects_each_boundary_not_only_final_library(self):
        for kind in ['same_avd','bytes','approval','execution','source','no_review','no_export','rejected_import','unconfirmed','changed_name']:
            pack,p=chain()
            if kind=='same_avd':p['targetAvd']=p['sourceAvd']
            elif kind=='bytes':p['targetBlob']+=b' '
            elif kind=='approval':p['pending']['approved']=json.dumps(pack['skill'])
            elif kind=='execution':p['after']['result']='new'
            elif kind=='source':p['sourceAfter']['library']='changed'
            elif kind=='no_review':p['reviewXml']=''
            elif kind=='no_export':p['exportXml']=''
            elif kind=='rejected_import':p['importXml']='<node text="File rejected"/>'
            elif kind=='unconfirmed':p['after']['storageUnconfirmed']='true'
            else:p['after']['library']=json.dumps([dict(pack,name='changed')])
            with self.subTest(kind=kind):self.assertFalse(chain_check(pack,p)['correctChain'])
    def test_missing_or_malformed_evidence_is_not_a_pass(self):
        pack,p=chain();del p['before'];self.assertFalse(chain_check(pack,p)['correctChain'])
        pack,p=chain();p['after']['library']='broken';self.assertFalse(chain_check(pack,p)['correctChain'])
    def test_restore_preserves_override_existence_and_null_font(self):
        a=display_state('Physical size: 720x1280','Physical density: 240','null')
        self.assertEqual(restore_commands(a),[['wm','size','reset'],['wm','density','reset'],['settings','delete','system','font_scale']])
        b=display_state('Physical size: 720x1280\nOverride size: 540x960','Physical density: 240\nOverride density: 320','1.15')
        self.assertEqual(restore_commands(b),[['wm','size','540x960'],['wm','density','320'],['settings','put','system','font_scale','1.15']])
    def test_fault_requires_public_nodes_on_the_relevant_page(self):
        def xml(page,keys):
            root=ET.Element('hierarchy');ET.SubElement(root,'node',{'resource-id':'edu.sydney.transferlab:id/wfPage','text':page})
            for key in keys:ET.SubElement(root,'node',{'resource-id':'edu.sydney.transferlab:id/'+key})
            return root
        self.assertTrue(fault_trigger('missing',xml('fan',['wfFanCancel','wfFanPower'])))
        self.assertFalse(fault_trigger('missing',xml('overview',[])))
        self.assertFalse(fault_trigger('missing',xml('fan',['wfFanSave'])))
        self.assertTrue(fault_trigger('duplicate',xml('lamp',['wfLampPower','wfLampPower'])))
        self.assertFalse(fault_trigger('duplicate',xml('lamp',['wfLampPower'])))
    def test_clickable_parent_does_not_allow_offscreen_or_ambiguous_rows(self):
        ui=ET.fromstring('<hierarchy><node bounds="[0,0][720,1280]"><node clickable="true" enabled="true"><node text="file" enabled="true" bounds="[10,100][300,140]"/></node></node></hierarchy>')
        self.assertEqual(visible_node(ui,lambda n:n.get('text')=='file'),[10,100,300,140])
        for kind in ['offscreen','disabled','disabled_parent','no_parent','duplicate','two_windows']:
            broken=copy.deepcopy(ui);leaf=next(n for n in broken.iter() if n.get('text')=='file')
            if kind=='offscreen':leaf.set('bounds','[10,1300][300,1280]')
            elif kind=='disabled':leaf.set('enabled','false')
            elif kind=='disabled_parent':next(n for n in broken.iter() if n.get('clickable')=='true').set('enabled','false')
            elif kind=='no_parent':next(n for n in broken.iter() if n.get('clickable')=='true').set('clickable','false')
            elif kind=='duplicate':broken[0].append(copy.deepcopy(leaf))
            else:broken.append(copy.deepcopy(broken[0]))
            with self.subTest(kind=kind),self.assertRaises(RuntimeError):visible_node(broken,lambda n:n.get('text')=='file')
    def test_ack_arriving_after_read_deadline_is_not_accepted(self):
        ui=ET.fromstring('<hierarchy><node text="Skill exported."/></hierarchy>')
        with patch('task4_files.time.monotonic',side_effect=[0,0,9]),patch('task4_files.device.tree',return_value=ui),patch('task4_files.snapshot') as capture:
            with self.assertRaisesRegex(RuntimeError,'UI_ACK_MISSING'):wait_marker('Skill exported.',None,'late')
            capture.assert_not_called()
    def test_duplicate_allows_navigation_but_never_switch_input(self):
        d=list(copy.deepcopy(sample()));skill=source_record('M1')['skill'];d[0]=skill
        r=d[2];r.update(traceId=skill['traceId'],traceSha256=skill['traceSha256'],status='UNCONFIRMED',reason='AMBIGUOUS:wfLampPower',completedSteps=0,terminalStepIndex=0,actions=r['actions'][:1])
        d[4]=[d[4][0]]+[e for e in d[4][1:] if e['kind'] in ['INPUT_REQUEST','INPUT_RETURN'] and e['stepIndex']==0]+[d[4][-1]]
        d[4][0]['data']=skill;d[4][1]['data']=skill['steps'][0];d[4][-1]['data']=copy.deepcopy(r)
        for n,e in enumerate(d[4],1):e['seq']=n
        d[3]['events']=d[3]['events'][:2];d[3]['fault']='duplicate';d[5]=[]
        for ms in [500,1500,5500]:
            e=copy.deepcopy(d[3]['events'][-1]);e.update(ms=ms,kind='audit_snapshot');d[3]['events'].append(e);d[5].append(copy.deepcopy(d[3]))
        d[6]=d[1][:]
        ui=ET.fromstring('<hierarchy><node resource-id="edu.sydney.transferlab:id/wfPage" text="lamp"/><node resource-id="edu.sydney.transferlab:id/wfLampPower"/><node resource-id="edu.sydney.transferlab:id/wfLampPower"/></hierarchy>')
        row=dict(flow='M1',fault='duplicate')
        score=fault_score(row,*d,ui);self.assertTrue(score['safeStop'],score['errors'])
        for kind in ['reason','not_triggered','switch_input','missing_audit','flow']:
            broken=copy.deepcopy(d);changed=copy.deepcopy(ui);mutated=dict(row)
            if kind=='reason':broken[2]['reason']='STEP_UNCONFIRMED'
            elif kind=='not_triggered':changed.remove(changed[-1])
            elif kind=='switch_input':broken[2]['actions'][0]['id']='wfLampPower'
            elif kind=='missing_audit':broken[5].pop(0)
            else:mutated['flow']='S3'
            with self.subTest(kind=kind):self.assertFalse(fault_score(mutated,*broken,changed)['safeStop'])


if __name__=='__main__':unittest.main()
