"""Task 2 wiring guards; native behavior is checked separately on Android."""
from pathlib import Path
import unittest
import copy
from task2_protocol import plan, summarize, recording_match, file_match, FLOWS
from test_flexible_workflow import trace
from workflow_contract import compile_evidence
from task2_device_checks import await_approved
from task2_recompute import validate_envelope, guide_match, recompute
from task2_file_checks import await_import_state,management_tap
from task2_negative_checks import protected_unchanged, stopped_invalid
from task2_audit_capture import metrics
from task2_result_bundle import negative_rows

JAVA = Path(__file__).resolve().parents[1]/'android-agent-probe/app/src/main/java/edu/sydney/probe'


class TeachingWiringTests(unittest.TestCase):
    def test_compiled_review_does_not_mutate_draft_before_validation(self):
        activity=(JAVA/'TeachingActivity.java').read_text(encoding='utf-8')
        self.assertNotIn('store.stage(raw)&&store.reviewNamed',activity)
        self.assertIn('store.reviewCompiled(raw,chosen)',activity)

    def test_imported_review_does_not_stage_before_name_and_capacity_validation(self):
        store=(JAVA/'WorkflowStore.java').read_text(encoding='utf-8')
        imported=store.split('boolean reviewImported(String expected)',1)[1].split('String name()',1)[0]
        self.assertNotIn('stage(item.raw)',imported)
        self.assertIn('writeReviewed(item.raw,item.name,expected)',imported)
        self.assertIn('editor.remove("pendingNamed")',store)

    def test_teaching_metadata_is_raw_and_not_length_filtered(self):
        activity=(JAVA/'TeachingActivity.java').read_text(encoding='utf-8')
        self.assertNotIn('saveName.setFilters',activity)
        self.assertIn('TeachingInput.goal(goal.getText().toString())',activity)
        self.assertIn('if(key.equals("teachPairing"))v.setFilters',activity)


class TeachingEvidenceTests(unittest.TestCase):
    def test_fixed_denominators_and_new_flows(self):
        p=plan();self.assertEqual(len(p['cases']),57)
        self.assertEqual(len({r['id'] for r in p['cases']}),57)
        result=summarize(p,[])
        self.assertEqual([g['planned'] for g in result['groups'].values()],[6,27,24])
        self.assertEqual(result['verdict'],'NOT_READY')

    def test_entire_sequence_is_required_not_only_final_state(self):
        for flow,actions in FLOWS.items():
            t=trace(actions);s=compile_evidence(t)
            with self.subTest(flow=flow):
                self.assertTrue(recording_match(t,s,actions))
                wrong=copy.deepcopy(s);wrong['steps'].reverse()
                self.assertFalse(recording_match(t,wrong,actions))
        t=trace(FLOWS['V']);s=compile_evidence(t);s['steps']=s['steps'][3:]
        self.assertFalse(recording_match(t,s,FLOWS['V']))

    def test_corrupt_and_wrong_origin_are_not_success(self):
        t=trace(FLOWS['P']);s=compile_evidence(t)
        for key,value in [('source','HUMAN_DECLARED'),('end','CANCELLED'),('error','missing')]:
            bad=copy.deepcopy(t);bad[key]=value
            with self.subTest(key=key):self.assertFalse(recording_match(bad,s,FLOWS['P']))

    def test_file_comparison_is_exact_bytes_not_decoded_similarity(self):
        self.assertTrue(file_match(b'{"a":1}',b'{"a":1}'))
        self.assertFalse(file_match(b'{"a":1}',b'{ "a":1}'))
        self.assertFalse(file_match(b'',b''))

    def test_unknown_duplicate_or_unproven_pass_rejected(self):
        for rows in ([dict(id='unknown',outcome='PASS')],
                     [dict(id='C-P-en',outcome='NOT_RUN')]*2,
                     [dict(id='C-P-en',outcome='PASS',facts={})],
                     [dict(id='C-P-en',outcome='SUCCEEDED')]):
            with self.subTest(rows=rows),self.assertRaises(ValueError):summarize(plan(),rows)

    def test_same_device_replay_cannot_be_scored_as_transfer(self):
        facts=dict(samePackage=True,differentDevice=False,reviewedOnTarget=True,
                   correctCompletion=True,orderedProcess=True,untouched=True,persisted=True)
        with self.assertRaises(ValueError):summarize(plan(),[dict(id='D-P-i0-r0',outcome='PASS',facts=facts)])


class TeachingSaveObservationTests(unittest.TestCase):
    def test_late_commit_is_observed_without_reclicking(self):
        import json
        skill=compile_evidence(trace(FLOWS['P']));ticks=[0];reads=[0]
        def read():
            reads[0]+=1
            return {'approved':json.dumps(skill if reads[0]>2 else {}),'library':json.dumps([{'skill':skill}])}
        def sleep(value):ticks[0]+=value
        self.assertEqual(json.loads(await_approved(skill,read,lambda:ticks[0],sleep)['approved']),skill)
        self.assertEqual(reads[0],3)

    def test_wrong_or_expired_commit_is_not_accepted(self):
        skill=compile_evidence(trace(FLOWS['P']));ticks=[0]
        def sleep(value):ticks[0]+=value
        with self.assertRaises(RuntimeError):await_approved(skill,lambda:{'approved':'{}'},lambda:ticks[0],sleep,timeout=.5)
        import json
        ticks[0]=0
        def late_read():
            ticks[0]=9
            return {'approved':json.dumps(skill),'library':json.dumps([{'skill':skill}])}
        with self.assertRaises(RuntimeError):await_approved(skill,late_read,lambda:ticks[0],sleep)

    def test_storage_failure_is_not_polled_into_success(self):
        skill=compile_evidence(trace(FLOWS['P']))
        with self.assertRaises(RuntimeError):await_approved(skill,lambda:{'storageUnconfirmed':'true'})


class TeachingIndependentAuditTests(unittest.TestCase):
    def example(self):
        skill=compile_evidence(trace(FLOWS['P']))
        result=dict(runId='audit-run',traceId=skill['traceId'],traceSha256=skill['traceSha256'],
                    startedMs=10,finishedMs=20,deadlineMs=100,status='SUCCEEDED',
                    actions=[dict(id=s['id'],sourceIndex=i,ms=10+i) for i,s in enumerate(skill['steps'],1)])
        case=dict(flow='P',initial=[0,40,0,3],caseId='fixture',sameDevice=True)
        oracle=dict(caseId='fixture',initial=case['initial'],events=[dict(ms=10),dict(ms=20)])
        journal=[dict(runId='audit-run',seq=1,ms=10,kind='START',data=skill),
                 dict(runId='audit-run',seq=2,ms=21,kind='RESULT',data=result)]
        return skill,result,case,oracle,journal

    def test_independent_audit_requires_exact_identity_and_order(self):
        values=self.example();self.assertTrue(validate_envelope(*values))
        for index,key,value in [(1,'traceId','foreign'),(2,'caseId','other'),
                                (1,'finishedMs',101),(2,'initial',[1,40,0,3])]:
            modified=copy.deepcopy(values);modified[index][key]=value
            with self.subTest(index=index,key=key),self.assertRaises(ValueError):validate_envelope(*modified)

    def test_rewritten_or_missing_journal_is_not_accepted(self):
        for mutation in ('gap','run','terminal','clock','start','actions','oracle_clock'):
            values=copy.deepcopy(self.example());skill,result,case,oracle,journal=values
            if mutation=='gap':journal[-1]['seq']=3
            elif mutation=='run':journal[-1]['runId']='another-run'
            elif mutation=='terminal':journal[-1]['data']={}
            elif mutation=='clock':journal[-1]['ms']=9
            elif mutation=='start':journal[0]['data']={}
            elif mutation=='actions':result['actions'].reverse()
            else:oracle['events'][-1]['ms']=9
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):validate_envelope(*values)

    def test_guide_keeps_every_save_object_and_actual_destination(self):
        skill=compile_evidence(trace(FLOWS['V']))
        guide=('1. Switch to single-page controls\n2. Set brightness to 20%\n'
               '3. Save lamp settings; stay on the single page\n4. Set brightness to 80%\n'
               '5. Save lamp settings; stay on the single page\n6. Switch to overview / Pages\n')
        self.assertTrue(guide_match(skill,guide))
        self.assertFalse(guide_match(skill,guide.replace('stay on the single page','return to overview')))
        self.assertFalse(guide_match(skill,guide.replace('2. Set brightness to 20%\n','')))

    def test_incomplete_recording_is_not_invented_as_pass(self):
        import tempfile,json
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'R-recording';folder.mkdir()
            (folder/'trace.json').write_text(json.dumps(trace(FLOWS['R'])),encoding='utf-8')
            value=recompute(Path(root))
            self.assertEqual(value['records']['R']['outcome'],'NOT_RUN')
            self.assertEqual(value['passed'],0)


class TeachingFileAcknowledgementTests(unittest.TestCase):
    def test_management_preparation_issues_only_one_visible_button_input(self):
        from unittest.mock import patch
        import xml.etree.ElementTree as ET
        ui=ET.fromstring('<node><node class="android.widget.ScrollView" bounds="[0,100][600,1000]">'
                         '<node resource-id="edu.sydney.probe:id/libraryTools" bounds="[10,200][400,250]" enabled="true"/></node></node>')
        with patch('task2_file_checks.tree',return_value=ui),patch('task2_file_checks.tap') as click,patch('task2_file_checks.adb') as input_:
            management_tap('libraryTools')
            click.assert_called_once_with('emulator-5554','libraryTools');input_.assert_not_called()

    def test_ambiguous_management_control_is_not_clicked(self):
        from unittest.mock import patch
        import xml.etree.ElementTree as ET
        ui=ET.fromstring('<node><node resource-id="edu.sydney.probe:id/libraryTools"/><node resource-id="edu.sydney.probe:id/libraryTools"/></node>')
        with patch('task2_file_checks.tree',return_value=ui),patch('task2_file_checks.tap') as click:
            with self.assertRaises(RuntimeError):management_tap('libraryTools')
            click.assert_not_called()

    def test_pending_and_review_ack_do_not_transfer_approval(self):
        import json
        pack=dict(skill=dict(traceId='source'));before=dict(approved='old',library='[]',result='old-result',draft='old')
        ticks=[0];reads=[0]
        def read():
            reads[0]+=1
            return dict(before,**({'pendingNamed':json.dumps(pack)} if reads[0]>1 else {}))
        def sleep(value):ticks[0]+=value
        state=await_import_state(pack,before,read=read,clock=lambda:ticks[0],sleep=sleep)
        self.assertEqual(state['approved'],'old');self.assertEqual(reads[0],2)
        reviewed=dict(approved=json.dumps(pack['skill']),library=json.dumps([pack]),result='old-result')
        self.assertEqual(await_import_state(pack,before,True,read=lambda:reviewed),reviewed)

    def test_injected_approval_and_late_review_are_not_accepted(self):
        pack=dict(skill={});before=dict(approved='old',library='[]',result='unchanged')
        with self.assertRaises(RuntimeError):await_import_state(pack,before,read=lambda:dict(before,approved='new'))
        ticks=[0]
        def read():
            ticks[0]=9
            return dict(approved='{}',library='[{"skill":{}}]',result='unchanged')
        with self.assertRaises(RuntimeError):await_import_state(pack,before,True,read=read,clock=lambda:ticks[0])


class TeachingNegativeCriteriaTests(unittest.TestCase):
    def test_negative_ledger_cannot_hide_extra_or_nonnegative_cases(self):
        row=dict(id='E-empty-0',outcome='NOT_RUN')
        self.assertEqual(negative_rows([row]),{row['id']:row})
        for rows in ([row,row],[dict(id='unknown',outcome='NOT_RUN')],
                     [dict(id='C-P-en',outcome='NOT_RUN')],[dict(id='E-empty-0',outcome='PASS',facts={})]):
            with self.subTest(rows=rows),self.assertRaises(ValueError):negative_rows(rows)

    def test_protected_fields_cannot_change_on_rejected_review(self):
        before=dict(approved='original',library='[original]',draft='prior',result='old')
        self.assertTrue(protected_unchanged(before,dict(before)))
        for key in before:
            with self.subTest(key=key):self.assertFalse(protected_unchanged(before,dict(before,**{key:'new'})))

    def test_complete_process_is_not_incomplete_counterexample(self):
        self.assertFalse(stopped_invalid(trace(FLOWS['P'])))
        for keys in ([],['wfOpenLamp','wfLampValue80'],['wfOpenLamp','wfLampValue80','wfLampCancel']):
            with self.subTest(keys=keys):self.assertTrue(stopped_invalid(trace(keys)))

    def test_recording_clock_domains_are_not_reported_as_exact_latency(self):
        t=trace(FLOWS['P']);events=[]
        for step in t['steps']:
            events += [dict(kind='SETTLE_OBSERVATION',decision='CHANGED',finishedMs=500,elapsedMs=4),
                       dict(kind='CHANGED',step=step)]
        audit=dict(traceId=t['traceId'],end='STOPPED',error='',events=events)
        measured=metrics(t,audit)
        self.assertEqual(measured['inputToConfirmation'],'NOT_MEASURED_CLOCK_DOMAINS_UNCALIBRATED')
        self.assertEqual(measured['observationCalls']['p50Ms'],4)
        events[1]['step']={}
        with self.assertRaises(ValueError):metrics(t,audit)


if __name__=='__main__':unittest.main()
