from pathlib import Path
import unittest
from unittest.mock import patch
ROOT=Path(__file__).parent
class Wiring(unittest.TestCase):
    def test_flow_success_is_checked_after_receipt_build_before_handoff(self):
        runner=(ROOT/'native/app/src/main/java/edu/sydney/probe/FlowAndroidRunner.java').read_text(encoding='utf-8')
        service=(ROOT/'native/app/src/main/java/edu/sydney/probe/ProbeService.java').read_text(encoding='utf-8')
        self.assertIn('finishReceipt(result,started,deadline,cancelled,"FLOW_RECEIPT_BUILT")',runner)
        self.assertIn('FlowCompletionBoundary.status(proposed,finished,deadline,cancelled.get())',runner)
        self.assertIn('latency.put("runtime_ms",finished-started)',runner)
        handoff=service.split('completion.accept(result);',1)[0]
        self.assertIn('if(flow!=null)FlowAndroidRunner.finishReceipt',handoff)
        self.assertLess(handoff.index('finishPortableEventScope(cancellation)'),handoff.index('FlowAndroidRunner.finishReceipt'))
        self.assertIn('put("verification_result",false).put("final_observation_complete",false)',runner)
    def test_scoped_reads_keep_whole_state_and_fresh_root_boundaries(self):
        runner=(ROOT/'native/app/src/main/java/edu/sydney/probe/FlowAndroidRunner.java').read_text(encoding='utf-8')
        port=(ROOT/'native/app/src/main/java/edu/sydney/probe/FlowLegacyPort.java').read_text(encoding='utf-8')
        self.assertIn('observe(port,"ENTRY")',runner)
        self.assertIn('observe(port,"FINAL")',runner)
        self.assertIn('observe(port,"AFTER."+id)',runner)
        self.assertIn('op.equals("CALL"))return observe',runner)
        self.assertIn('var frame=source.read()',port)
        self.assertIn('put("complete",properties.equals(pkg.binding.targets.keySet()))',port)
    def test_live_review_guard_pins_exact_bytes_without_recursive_decode(self):
        source=(ROOT/'native/app/src/main/java/edu/sydney/probe/FlowAndroidRunner.java').read_text(encoding='utf-8')
        guard=source.split('boolean localKnowledgeCurrent',1)[1].split('private void validate',1)[0]
        self.assertIn('reviewedBytesUnchanged(localKnowledge)',guard)
        self.assertNotIn('.approved()',guard)
        self.assertIn('store.decode(raw)',source)
        store=(ROOT/'native/app/src/main/java/edu/sydney/probe/FlowKnowledgeStore.java').read_text(encoding='utf-8')
        live=store.split('boolean reviewedBytesUnchanged',1)[1].split('static void replace',1)[0]
        self.assertIn('openFileInput("published-flow-local.json")',live)
        self.assertIn('getSharedPreferences("flow_knowledge_review",0)',live)
        self.assertIn('pinned.matches(raw,',live)
        reviewed=(ROOT/'native/app/src/main/java/edu/sydney/probe/FlowReviewedBytes.java').read_text(encoding='utf-8')
        self.assertIn('hash.equals(currentApproval)&&raw.equals(currentRaw)',reviewed)
        self.assertIn('hash.equals(FlowDigest.sha256(raw))',reviewed)
    def test_current_root_keeps_live_window_and_target_guards(self):
        source=(ROOT/'native/app/src/main/java/edu/sydney/probe/ProbeService.java').read_text(encoding='utf-8')
        self.assertIn('root=getRootInActiveWindow()',source)
        self.assertIn('PortableWindowReadPolicy.postRootFailure',source)
        self.assertIn('PortableWindowGuard.frame(root,windows)',source)
    def test_receiver_releases_broadcast_before_runtime_completion(self):
        source=(ROOT/'native/app/src/main/java/edu/sydney/probe/FlowAuditReceiver.java').read_text()
        self.assertIn('result->write(context,id,result)',source)
        self.assertNotIn('finally{pending.finish();}',source)
    def test_empty_write_authority_is_transported_not_dropped(self):
        import lab_transport
        seen=[]
        def fake(host,*args,**kwargs):
            seen.append(args)
            return b'{"final_status":"REJECTED"}'
        with patch.object(lab_transport,'adb',fake):
            lab_transport.execute('emulator-5556',{'actual_write_set':[]},writes=[])
        command=next(a for a in seen if 'broadcast' in a)
        self.assertEqual(command[command.index('allowed_writes')+1],"''")
    def test_actual_service_entry(self):
        source=(ROOT/'native/app/src/main/java/edu/sydney/probe/ProbeService.java').read_text(encoding='utf-8')
        self.assertIn('runFlow(',source)
        self.assertIn('FlowAndroidRunner',source)
    def test_flow_does_not_use_oracle(self):
        path=ROOT/'native/app/src/main/java/edu/sydney/probe/FlowAndroidRunner.java'
        self.assertTrue(path.exists())
        text=path.read_text(encoding='utf-8')
        self.assertNotIn('run-as',text)
        self.assertNotIn('oracle',text.lower())
        self.assertIn('FlowLegacyPort',text)
if __name__=='__main__':unittest.main()
