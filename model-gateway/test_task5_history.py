"""Historical normalization keeps phases and unrun slots distinct."""
import tempfile
import unittest
from pathlib import Path
from task5_history import task4_blocked, evidence_summary, collect_tree, remote_identity
from task5_evidence import ReceiptReader


class HistoryTests(unittest.TestCase):
    def test_response_identity_must_not_repeat(self):
        seen=set();remote_identity(dict(request_id='resp_x'),seen)
        with self.assertRaises(ValueError):remote_identity(dict(request_id='resp_x'),seen)
        with self.assertRaises(ValueError):remote_identity(dict(request_id=''),seen)
    def test_task4_cannot_pass_from_installation_or_failure_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            r=ReceiptReader(tmp);value=task4_blocked(r)
            self.assertEqual(value['summary']['groups']['chain']['NOT_RUN'],3)
            self.assertEqual(value['summary']['groups']['normal']['NOT_RUN'],216)
            self.assertEqual(value['summary']['transferValidation'],'NOT_READY')

    def test_scored_and_planned_denominators_and_no_pooled_stops(self):
        value=evidence_summary([dict(id='a',state='PASS',elapsedMs=1),dict(id='b',state='NOT_RUN')])
        self.assertEqual(value['passScored']['denominator'],1)
        self.assertEqual(value['passPlanned']['denominator'],2)
        self.assertEqual(value['latencyAll']['missing'],1)

    def test_unknown_state_duplicate_id_and_bool_time_rejected(self):
        for rows in [[dict(id='a',state='bad')],[dict(id='a',state='PASS')]*2,[dict(id='a',state='PASS',elapsedMs=True)]]:
            with self.subTest(rows=rows),self.assertRaises(ValueError):evidence_summary(rows)

    def test_collect_tree_never_copies_binary_or_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'a';p.mkdir();(p/'x.json').write_text('{}');(p/'x.apk').write_bytes(b'sk-proj-PRIVATE')
            r=ReceiptReader(tmp);collect_tree(r,'a')
            self.assertEqual(set(r.receipts),{'a/x.json'})
