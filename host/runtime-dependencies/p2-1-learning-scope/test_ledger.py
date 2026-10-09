from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from learning_ledger import LearningLedger
from learning_scope import ScopeError
from test_scope import scope_fixture


def cost_event(event_id='cost.demo', **updates):
    event = {'kind': 'HUMAN_COST', 'event_id': event_id, 'activity_id': 'activity.' + event_id,
             'source_ids': ['src.demo'], 'category': 'DEMONSTRATION', 'actor': 'HUMAN',
             'amount': 1, 'unit': 'count', 'evidence_refs': ['fixture.demo'],
             'supersedes_event_id': None}
    event.update(updates)
    return event


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='p21-ledger-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'learning.sqlite3'
        self.scope = scope_fixture()
        self.store = LearningLedger.create(self.path, self.scope)

    def test_create_reopen_preserves_scope_and_never_exports_authority(self):
        self.store.append(cost_event(), expected_revision=0)
        reopened = LearningLedger.open(self.path)
        result = reopened.inspect()
        self.assertEqual(result['scope'], self.scope)
        self.assertEqual(result['revision'], 1)
        self.assertFalse(result['execution_authority'])
        self.assertNotIn('authorization', result)

    def test_unknown_cost_is_not_zero_and_zero_can_be_explicit(self):
        self.store.append(cost_event(amount=None), expected_revision=0)
        metric = self.store.inspect()['human_cost']['DEMONSTRATION']
        self.assertIsNone(metric['total'])
        self.assertEqual(metric['unmeasured_entries'], 1)
        self.assertFalse(metric['complete'])
        event = cost_event('cost.measured', amount=0, activity_id='activity.cost.demo',
                           supersedes_event_id='cost.demo')
        self.store.append(event, expected_revision=1)
        metric = self.store.inspect()['human_cost']['DEMONSTRATION']
        self.assertEqual(metric['total'], 0)
        self.assertEqual(len(self.store.inspect()['events']), 2)

    def test_each_cost_category_and_units_are_measurable(self):
        amounts = {'DEMONSTRATION': 1, 'ANNOTATION': 3, 'REVIEW': 1500,
                   'CORRECTION': 2500, 'PRECONFIGURATION': 5000}
        for index, (category, amount) in enumerate(amounts.items()):
            self.store.append(cost_event('cost.' + category.lower(), category=category,
                                         amount=amount, unit='count' if index < 2 else 'ms'),
                              expected_revision=index)
        result = self.store.inspect()['human_cost']
        self.assertEqual({key: value['total'] for key, value in result.items()}, amounts)

    def test_automated_demo_is_separate_and_not_invented_human_effort(self):
        self.scope['sources'][0]['actor'] = 'AUTOMATED'
        path = Path(self.temp.name) / 'auto.sqlite3'
        store = LearningLedger.create(path, self.scope)
        store.append(cost_event(actor='AUTOMATED'), expected_revision=0)
        result = store.inspect()
        self.assertEqual(result['automated_cost']['DEMONSTRATION']['total'], 1)
        self.assertIsNone(result['human_cost']['DEMONSTRATION']['total'])
        self.assertEqual(result['scope']['sources'][0]['actor'], 'AUTOMATED')

    def test_model_generation_cannot_hide_sources_or_human_cost(self):
        self.store.append(cost_event(), expected_revision=0)
        event = {'kind': 'GENERATION', 'event_id': 'gen.fake', 'source_ids': ['src.demo'],
                 'channel': 'FAKE_MODEL', 'output_sha256': 'b' * 64, 'evidence_ref': 'fixture.generated'}
        self.store.append(event, expected_revision=1)
        result = self.store.inspect()
        self.assertEqual(result['human_cost']['DEMONSTRATION']['total'], 1)
        self.assertEqual(result['scope']['sources'], self.scope['sources'])
        self.assertEqual(result['events'][1]['channel'], 'FAKE_MODEL')
        self.assertFalse(result['execution_authority'])

    def test_unknown_sources_extra_fields_invalid_types_and_units_rejected(self):
        cases = [dict(source_ids=['missing']), dict(amount=-1), dict(amount=True), dict(amount='1'),
                 dict(unit='minutes'), dict(approved=True), dict(evidence_refs=[])]
        for change in cases:
            with self.subTest(change=change), self.assertRaises(ScopeError):
                self.store.append(cost_event(**change), expected_revision=0)
        self.assertEqual(self.store.inspect()['revision'], 0)

    def test_duplicate_events_activities_and_revision_conflicts_rejected(self):
        self.store.append(cost_event(), expected_revision=0)
        for event, revision in ((cost_event(), 1),
                                (cost_event('cost.other', activity_id='activity.cost.demo'), 1),
                                (cost_event('cost.fresh'), 0)):
            with self.subTest(event=event['event_id']), self.assertRaises(ScopeError):
                self.store.append(event, expected_revision=revision)
        self.assertEqual(self.store.inspect()['revision'], 1)

    def test_correction_cannot_change_actor_category_or_source(self):
        self.store.append(cost_event(), expected_revision=0)
        for change in (dict(actor='AUTOMATED'), dict(category='ANNOTATION'), dict(activity_id='other')):
            event = cost_event('cost.corrected', activity_id='activity.cost.demo',
                               supersedes_event_id='cost.demo', **change) if 'activity_id' not in change else cost_event(
                                   'cost.corrected', supersedes_event_id='cost.demo', **change)
            with self.subTest(change=change), self.assertRaises(ScopeError):
                self.store.append(event, expected_revision=1)
        self.assertEqual(self.store.inspect()['human_cost']['DEMONSTRATION']['total'], 1)

    def test_unknown_actor_prevents_claiming_complete_human_cost(self):
        self.store.append(cost_event(actor='UNKNOWN', amount=1), expected_revision=0)
        metric = self.store.inspect()['human_cost']['DEMONSTRATION']
        self.assertIsNone(metric['total'])
        self.assertFalse(metric['complete'])

    def test_open_missing_corrupt_or_schema_mismatched_does_not_recreate(self):
        missing = Path(self.temp.name) / 'missing.sqlite3'
        with self.assertRaises(ScopeError):
            LearningLedger.open(missing)
        self.assertFalse(missing.exists())
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE scope_record SET schema_version='future'")
        with self.assertRaises(ScopeError):
            LearningLedger.open(self.path)
        self.assertTrue(self.path.exists())

    def test_scope_or_event_digest_corruption_is_not_silently_accepted(self):
        self.store.append(cost_event(), expected_revision=0)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("UPDATE events SET sha256=?", ('c' * 64,))
        with self.assertRaises(ScopeError):
            self.store.inspect()

    def test_create_existing_never_overwrites(self):
        before = self.path.read_bytes()
        with self.assertRaises(ScopeError):
            LearningLedger.create(self.path, self.scope)
        self.assertEqual(before, self.path.read_bytes())

    def test_mutated_inputs_and_inspection_do_not_rewrite_original(self):
        event = cost_event()
        self.store.append(event, expected_revision=0)
        event['amount'] = 999
        snapshot = self.store.inspect()
        snapshot['scope']['modes'] = ['AUTO_UI']
        snapshot['events'][0]['amount'] = 0
        self.assertEqual(self.store.inspect()['human_cost']['DEMONSTRATION']['total'], 1)

    def test_double_supersede_and_superseding_generation_rejected(self):
        self.store.append(cost_event(amount=None), expected_revision=0)
        corrected = cost_event('cost.correction', activity_id='activity.cost.demo',
                               supersedes_event_id='cost.demo')
        self.store.append(corrected, expected_revision=1)
        with self.assertRaises(ScopeError):
            self.store.append(cost_event('cost.duplicate', activity_id='activity.cost.demo',
                                         supersedes_event_id='cost.demo'), expected_revision=2)


if __name__ == '__main__':
    unittest.main()
