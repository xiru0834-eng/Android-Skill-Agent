"""Pure DTO tests, never Android observations."""
import copy
import json
import unittest

from observation_tree import ObservationError, copy_tree


def raw_node(local='0', parent=None, **changes):
    value = {'node_local_id': local, 'parent_local_id': parent,
             'package': 'edu.sydney.parameterroom', 'resource_id': None,
             'class_name': 'android.widget.LinearLayout', 'role': 'container',
             'text': None, 'content_description': None, 'bounds': [0, 0, 100, 100],
             'visible': True, 'enabled': True, 'clickable': False, 'checkable': False,
             'checked': None, 'selected': False, 'editable': False, 'password': False,
             'heading': False, 'range': None, 'collection': None, 'collection_item': None}
    value.update(changes)
    return value


def raw_tree(nodes=None, **changes):
    value = {'nodes': nodes if nodes is not None else [raw_node()],
             'root_readable': True, 'complete': True, 'truncated_reasons': []}
    value.update(changes)
    return value


class TreeTests(unittest.TestCase):
    def test_duplicate_resource_ids_keep_distinct_parented_elements(self):
        raw = raw_tree([raw_node(), raw_node('0.0', '0', resource_id='app:id/duplicate'),
                        raw_node('0.1', '0', resource_id='app:id/duplicate')])
        tree = copy_tree(raw)
        self.assertEqual(len(tree['nodes']), 3)
        self.assertEqual(tree['nodes'][0]['children_local_ids'], ['0.0', '0.1'])
        raw['nodes'][1]['text'] = 'mutated'
        self.assertIsNone(tree['nodes'][1]['text'])

    def test_unknown_or_live_fields_are_rejected(self):
        for field, value in [('node', object()), ('performAction', lambda: None), ('permit', True)]:
            with self.subTest(field=field):
                raw = raw_tree(); raw['nodes'][0][field] = value
                with self.assertRaises(ObservationError): copy_tree(raw)

    def test_local_ids_are_unique_and_parent_graph_must_be_connected(self):
        cases = [[raw_node(), raw_node()], [raw_node(), raw_node('a', 'missing')],
                 [raw_node(), raw_node('a', 'b'), raw_node('b', 'a')],
                 [raw_node(), raw_node('a', None)]]
        for nodes in cases:
            with self.subTest(nodes=len(nodes)):
                with self.assertRaises(ObservationError): copy_tree(raw_tree(nodes))

    def test_password_editable_and_credentials_are_redacted_before_digest(self):
        nodes = [raw_node(), raw_node('a', '0', text='private', editable=True),
                 raw_node('b', '0', text='secret', password=True),
                 raw_node('c', '0', content_description='sk-proj-' + 'a' * 30)]
        encoded = json.dumps(copy_tree(raw_tree(nodes)))
        self.assertNotIn('private', encoded); self.assertNotIn('secret', encoded)
        self.assertNotIn('sk-proj', encoded); self.assertIn('REDACTED', encoded)

    def test_node_budget_threshold_marks_known_scope(self):
        for size in (2047, 2048, 2049):
            with self.subTest(size=size):
                tree = copy_tree(raw_tree([raw_node()] + [raw_node('n'+str(i), '0') for i in range(size-1)]))
                self.assertEqual(len(tree['nodes']), min(size, 2048))
                self.assertEqual(tree['complete'], size <= 2048)
                if size > 2048: self.assertIn('NODE_LIMIT', tree['truncated_reasons'])

    def test_depth_and_text_budget_are_visible_not_silently_complete(self):
        nodes = [raw_node()]
        for i in range(1, 66): nodes.append(raw_node(str(i), '0' if i == 1 else str(i-1)))
        tree = copy_tree(raw_tree(nodes))
        self.assertIn('DEPTH_LIMIT', tree['truncated_reasons'])
        text_tree = copy_tree(raw_tree([raw_node(text='x' * 257)]))
        self.assertEqual(len(text_tree['nodes'][0]['text']), 256)
        self.assertIn('TEXT_LIMIT', text_tree['truncated_reasons'])

    def test_root_missing_stale_and_legacy_flat_list_do_not_become_page_memory(self):
        for raw in (raw_tree(root_readable=False), {'nodes': []}, [], {'kind': 'WORKFLOW_TRACE'}):
            with self.subTest(value=type(raw).__name__):
                with self.assertRaises(ObservationError): copy_tree(raw)

    def test_wrong_types_ranges_and_bounds_fail_explicitly(self):
        cases = [{'visible': 1}, {'bounds': [0, 0, -1, 2]}, {'range': {'min': 0, 'max': 100, 'value': 101, 'kind': 'float'}},
                 {'text': float('nan')}, {'checked': 'true'}]
        for changes in cases:
            with self.subTest(changes=list(changes)):
                with self.assertRaises(ObservationError): copy_tree(raw_tree([raw_node(**changes)]))

    def test_full_digest_changes_with_dynamic_values_and_snapshot_ids_are_new(self):
        a = copy_tree(raw_tree([raw_node(range={'min': 0, 'max': 100, 'value': 20, 'kind': 'int'})]))
        b = copy_tree(raw_tree([raw_node(range={'min': 0, 'max': 100, 'value': 80, 'kind': 'int'})]))
        self.assertNotEqual(a['full_digest'], b['full_digest'])
        self.assertNotEqual(a['snapshot_id'], b['snapshot_id'])

    def test_valid_range_and_input_are_detached(self):
        original = raw_tree([raw_node(range={'min': 0, 'max': 100, 'value': 0, 'kind': 'int'})])
        before = copy.deepcopy(original); copied = copy_tree(original)
        self.assertEqual(original, before)
        self.assertEqual(copied['nodes'][0]['range']['value'], 0)


if __name__ == '__main__': unittest.main()
