import copy
import json
import unittest

from contracts import ContractError, load_json, validate_trace, validate_draft, to_v2


def trace_fixture():
    pkg = 'edu.sydney.transferlab'
    ids = [pkg + ':id/switchOne', pkg + ':id/switchTwo']
    return dict(kind='TRACE_BUNDLE', schemaVersion=1,
                traceId='12345678-1234-1234-1234-123456789abc', appPackage=pkg,
                appVersion='fixture', goal='Turn both switches on', source='ADB_TEST',
                end='STOPPED', observationScope='TARGET_STATES_ONLY', visualEvidence='NOT_COLLECTED',
                steps=[dict(index=i+1, targetId=target, eventTime=100+i,
                            before='checked=false', after='checked=true', outcome='CHANGED')
                       for i, target in enumerate(ids)],
                finalState=dict.fromkeys(ids, 'checked=true'),
                unattributedChanges=0, unsupportedClicks=0, overflowClicks=0)


def draft_fixture():
    return dict(status='candidate', reason='Two verified boolean changes.',
                steps=[dict(sourceIndex=1, role='First switch', desired=True),
                       dict(sourceIndex=2, role='Second switch', desired=True)])


class ContractTests(unittest.TestCase):
    def test_valid_trace_is_accepted(self):
        t = trace_fixture()
        self.assertEqual(validate_trace(t), t)

    def test_trace_abuse_cases_rejected(self):
        mutations = [lambda t: t.update(end='INTERRUPTED'),
                     lambda t: t.update(source='HUMAN_PROVEN'),
                     lambda t: t.update(schemaVersion=True),
                     lambda t: t.update(goal=''),
                     lambda t: t.update(approved=True),
                     lambda t: t.update(unsupportedClicks=1),
                     lambda t: t.update(unattributedChanges=False),
                     lambda t: t['steps'].pop(),
                     lambda t: t['steps'][1].update(targetId=t['steps'][0]['targetId']),
                     lambda t: t['steps'][1].update(index=1),
                     lambda t: t['steps'][1].update(eventTime=1),
                     lambda t: t['steps'][0].update(eventTime=-1),
                     lambda t: t['steps'][0].update(before='checked=true'),
                     lambda t: t['steps'][0].update(after=None),
                     lambda t: t['steps'][0].update(outcome='RAPID_UNCONFIRMED'),
                     lambda t: t['finalState'].update({t['steps'][0]['targetId']: 'checked=false'}),
                     lambda t: t.update(appPackage='com.private.bank'),
                     lambda t: t.update(goal='sk-proj-' + 'x'*30)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                t = trace_fixture(); mutate(t)
                with self.assertRaises(ContractError): validate_trace(t)

    def test_json_duplicate_and_nonfinite_rejected(self):
        for raw in ['{"a":1,"a":2}', '{"x":NaN}', '', '[]', 'x'*65537]:
            with self.subTest(raw=raw[:40]), self.assertRaises(ContractError): load_json(raw)

    def test_candidate_preserves_all_targets_and_v2_contract(self):
        trace, draft = trace_fixture(), draft_fixture()
        before = copy.deepcopy(trace)
        self.assertEqual(validate_draft(draft, trace), draft)
        skill = to_v2(draft, trace)
        self.assertEqual(skill['operation'], 'SET_TWO_CHECKED')
        self.assertEqual(skill['schemaVersion'], 2)
        self.assertEqual(len(skill['steps']), 2)
        self.assertEqual(skill['steps'][1]['resourceId'], trace['steps'][1]['targetId'])
        self.assertEqual(set(skill), {'schemaVersion', 'operation', 'appPackage', 'steps'})
        self.assertEqual(trace, before)

    def test_model_cannot_change_evidence_or_approve(self):
        mutations = [lambda d: d.update(approved=True), lambda d: d.update(status='execute'),
                     lambda d: d['steps'].pop(), lambda d: d['steps'].append(d['steps'][0]),
                     lambda d: d['steps'].reverse(),
                     lambda d: d['steps'][0].update(desired=False),
                     lambda d: d['steps'][0].update(desired=1),
                     lambda d: d['steps'][0].update(sourceIndex=True),
                     lambda d: d['steps'][0].update(targetId='fabricated'),
                     lambda d: d['steps'][0].update(role=''),
                     lambda d: d['steps'][0].update(role='sk-proj-'+'x'*30)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                draft = draft_fixture(); mutate(draft)
                with self.assertRaises(ContractError): validate_draft(draft, trace_fixture())

    def test_rejection_or_clarification_never_exports_skill(self):
        for status in ('reject', 'clarify'):
            d = dict(status=status, reason='Need another demonstration.', steps=[])
            self.assertEqual(validate_draft(d, trace_fixture()), d)
            with self.assertRaises(ContractError): to_v2(d, trace_fixture())


if __name__ == '__main__': unittest.main()
