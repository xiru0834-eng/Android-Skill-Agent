import tempfile
import unittest
from pathlib import Path
from accuracy_confirmation import freeze
from test_accuracy_confirmation import skills
from accuracy_evidence_export import export_campaign
from workflow_experiment import write


class AccuracyExportTests(unittest.TestCase):
    def test_framework_keeps_all_unrun_trials_without_completion_claim(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source';freeze(source,skills())
            report=export_campaign(source,Path(root)/'report')
            self.assertEqual(report['stages']['language']['states']['NOT_RUN'],360)
            self.assertIsNone(report['stages']['language']['actual_completion']['value'])

    def test_changed_frozen_labels_prevent_export(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source';freeze(source,skills())
            (source/'protocol.json').write_text('{}')
            with self.assertRaises(ValueError):export_campaign(source,Path(root)/'report')

    def test_recorded_request_error_is_failed_availability_not_safe_rejection(self):
        with tempfile.TemporaryDirectory() as root:
            source=Path(root)/'source';protocol=freeze(source,skills());trial=protocol['trials'][0]
            case=protocol['cases'][trial['index']];strategy=trial['strategy']
            if strategy=='G':from skill_selection import build_request
            else:from jev_selection import build_request
            folder=source/'trials'/f'000-{strategy}';folder.mkdir(parents=True)
            write(folder/'request.json',build_request(case['text'],case['skills']))
            write(source/'results.json',[dict(case=case,strategy=strategy,repeat=trial['repeat'],available=False,
                error='HTTP_429',remoteCalls=1,ms=20)])
            report=export_campaign(source,Path(root)/'report')
            states=report['stages']['language']['states']
            self.assertEqual(states['FAIL'],1);self.assertEqual(states['INVALID'],0)
            self.assertEqual(states['NOT_RUN'],359)


if __name__=='__main__':unittest.main()
