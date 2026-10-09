"""Adversarial independent re-audit; synthetic traces are not Android results."""
import copy
import unittest
from test_task3_workflows import sample
from task3_audit import rejudge


def complete():
    data=list(copy.deepcopy(sample()));original=data[3];samples=[]
    for ms in [500,1500,5500]:
        end=copy.deepcopy(original['events'][-1]);end.update(ms=ms,kind='audit_snapshot')
        original['events'].append(end);samples.append(copy.deepcopy(original))
    data[3]=copy.deepcopy(original);data[5]=samples
    return data


class AuditTests(unittest.TestCase):
    def test_three_fresh_prefix_audits_pass(self):
        value=rejudge(*complete());self.assertTrue(value['correctCompletion'],value['errors'])
    def test_fake_short_or_rewritten_audits_rejected(self):
        for kind in ['two','not_fresh','too_early','rewritten']:
            data=complete()
            if kind=='two':data[5].pop(0)
            elif kind=='not_fresh':data[5][0]['events'][-1]['kind']='input:wfLampSave'
            elif kind=='too_early':data[5][-1]['events'][-1]['ms']=1000;data[3]=copy.deepcopy(data[5][-1])
            else:data[5][0]['events'][1]['draft'][2]=1
            with self.subTest(kind=kind):self.assertFalse(rejudge(*data)['correctCompletion'])
    def test_foreign_transient_mutation_cannot_hide_between_confirmations(self):
        data=complete();events=data[3]['events'];foreign=copy.deepcopy(events[1]);foreign.update(ms=105,kind='unexpected_state');foreign['draft'][2]=1
        restored=copy.deepcopy(events[1]);restored.update(ms=110,kind='restored_state')
        events[2:2]=[foreign,restored]
        data[5]=[{**copy.deepcopy(data[3]),'events':copy.deepcopy(events[:i])} for i in [len(events)-2,len(events)-1,len(events)]]
        value=rejudge(*data);self.assertFalse(value['correctCompletion']);self.assertIn('UNEXPECTED_INTERMEDIATE_LEDGER_STATE',value['errors'])
    def test_clock_sequence_and_pending_do_not_accept_boolean_or_float(self):
        for kind in ['clock','pending','seq','finished']:
            data=complete()
            if kind=='clock':
                data[3]['events'][0]['ms']=1.0
                for audit in data[5]:audit['events'][0]['ms']=1.0
            elif kind=='pending':
                data[3]['events'][0]['pending']=False
                for audit in data[5]:audit['events'][0]['pending']=False
            elif kind=='seq':data[4][0]['seq']=True
            else:data[2]['finishedMs']=400.0
            with self.subTest(kind=kind):self.assertFalse(rejudge(*data)['correctCompletion'])


if __name__=='__main__':unittest.main()
