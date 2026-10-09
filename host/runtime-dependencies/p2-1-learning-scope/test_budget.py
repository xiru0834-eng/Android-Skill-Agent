import unittest

from learning_budget import LearningBudget
from learning_scope import ScopeError, scope_digest
from test_scope import scope_fixture


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.time = 1000
        self.scope = scope_fixture()
        self.scope['budgets'].update(max_actions=2, max_model_requests=1, max_storage_bytes=10)
        self.budget = LearningBudget(self.scope, clock=lambda: self.time)

    def test_each_dimension_accumulates_and_equality_allowed(self):
        for key, maximum in (('observations', 10), ('actions', 2), ('model_requests', 1), ('storage_bytes', 10)):
            with self.subTest(key=key):
                counter = LearningBudget(self.scope, clock=lambda: self.time)
                counter.charge({key: maximum})
                self.assertEqual(counter.snapshot()['spent'][key], maximum)
                with self.assertRaises(ScopeError):
                    counter.charge({key: 1})
                self.assertEqual(counter.snapshot()['status'], 'BUDGET_EXCEEDED')

    def test_zero_model_and_action_budgets_are_not_default_permission(self):
        for key in ('actions', 'model_requests'):
            with self.subTest(key=key):
                counter = LearningBudget(scope_fixture(), clock=lambda: self.time)
                with self.assertRaises(ScopeError):
                    counter.charge({key: 1})
                self.assertFalse(counter.snapshot()['execution_authority'])

    def test_combined_reservation_is_atomic(self):
        self.budget.charge({'actions': 1, 'storage_bytes': 5})
        with self.assertRaises(ScopeError):
            self.budget.charge({'actions': 1, 'storage_bytes': 6})
        self.assertEqual(self.budget.snapshot()['spent']['actions'], 1)
        self.assertEqual(self.budget.snapshot()['spent']['storage_bytes'], 5)

    def test_replanning_does_not_reset_total_deadline(self):
        self.time = 5999
        self.budget.charge({'observations': 1})
        self.time = 6000
        with self.assertRaises(ScopeError):
            self.budget.charge({'observations': 1})
        self.assertEqual(self.budget.snapshot()['status'], 'TIMEOUT')

    def test_cancel_is_terminal(self):
        self.budget.cancel()
        self.budget.cancel()
        with self.assertRaises(ScopeError):
            self.budget.charge({'actions': 1})
        self.assertEqual(self.budget.snapshot()['spent']['actions'], 0)
        self.assertEqual(self.budget.snapshot()['status'], 'CANCELLED')

    def test_environment_and_scope_changes_terminate(self):
        for field in ('scope_hash', 'environment'):
            counter = LearningBudget(self.scope, clock=lambda: self.time)
            params = {field: 'wrong'}
            with self.subTest(field=field), self.assertRaises(ScopeError):
                counter.charge({'observations': 1}, **params)
            self.assertIn(counter.snapshot()['status'], ('SCOPE_CHANGED', 'ENVIRONMENT_CHANGED'))

    def test_clock_backwards_or_invalid_stops(self):
        for bad in (999, True, 1.0, None):
            counter = LearningBudget(self.scope, clock=lambda: self.time)
            self.time = bad
            with self.subTest(bad=bad), self.assertRaises(ScopeError):
                counter.charge({'observations': 1})
            self.assertEqual(counter.snapshot()['status'], 'CLOCK_ERROR')
            self.time = 1000

    def test_invalid_charges_never_change_counters(self):
        for bad in ({}, {'actions': -1}, {'actions': True}, {'actions': '1'}, {'actions': 1.0}, {'other': 1}):
            with self.subTest(bad=bad), self.assertRaises(ScopeError):
                self.budget.charge(bad)
        self.assertEqual(self.budget.snapshot()['spent']['actions'], 0)

    def test_detached_input_and_snapshot_cannot_increase_limits(self):
        self.scope['budgets']['max_actions'] = 1000
        snapshot = self.budget.snapshot()
        snapshot['spent']['actions'] = -1000
        self.budget.charge({'actions': 2}, scope_hash=scope_digest(scope_fixture_with_budget()))
        with self.assertRaises(ScopeError):
            self.budget.charge({'actions': 1})


def scope_fixture_with_budget():
    scope = scope_fixture()
    scope['budgets'].update(max_actions=2, max_model_requests=1, max_storage_bytes=10)
    return scope


if __name__ == '__main__':
    unittest.main()
