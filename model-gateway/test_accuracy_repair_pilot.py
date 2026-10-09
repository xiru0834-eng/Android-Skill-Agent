import unittest
from test_accuracy_confirmation import skills
from accuracy_repair_pilot import pilot_cases, measure, summarize
from test_selection_accuracy import response


class RepairPilotTests(unittest.TestCase):
    def test_new_matrix_has_eight_intents_balanced_labels(self):
        cases=pilot_cases(skills())
        self.assertEqual(len(cases),16)
        self.assertEqual(sum(bool(c['expected']) for c in cases),8)
        self.assertEqual(len({c['conceptId'] for c in cases}),8)

    def test_guarded_missing_name_records_zero_calls(self):
        case=next(c for c in pilot_cases(skills()) if c['conceptId']=='missing-name' and c['language']=='en')
        row=measure('H',case,None,transport=lambda _:self.fail('API called'))
        self.assertTrue(row['correct']);self.assertEqual(row['remoteCalls'],0)

    def test_unrun_items_are_not_silently_removed(self):
        report=summarize([])
        self.assertEqual(report['planned'],128);self.assertEqual(report['notRun'],128)


if __name__=='__main__':unittest.main()
