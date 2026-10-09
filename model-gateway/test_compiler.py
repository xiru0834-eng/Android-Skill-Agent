import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from unittest.mock import patch
import urllib.error

from compiler import compile_trace, build_request, parse_response, ModelError, run_job, remote, NoRedirect
from contracts import ContractError
from test_contracts import trace_fixture, draft_fixture


def response(draft=None, status='completed'):
    return dict(model='gpt-6-sol', id='response-test', status=status,
                output=[dict(type='message', content=[dict(type='output_text', text=json.dumps(draft or draft_fixture()))])],
                usage=dict(input_tokens=100, output_tokens=50))


class CompilerTests(unittest.TestCase):
    def test_missing_key_never_opens_network(self):
        with patch.dict('os.environ', {}, clear=True), patch('compiler.urllib.request.build_opener') as opener:
            with self.assertRaisesRegex(ModelError, 'MISSING_API_KEY'): remote({})
            opener.assert_not_called()

    def test_auth_failure_does_not_echo_error_or_retry(self):
        failure = urllib.error.HTTPError('https://api.openai.com/v1/responses', 401, 'sensitive-detail', {}, None)
        with patch.dict('os.environ', {'OPENAI_API_KEY':'unit-test-placeholder'}), \
             patch('compiler.urllib.request.build_opener') as factory:
            factory.return_value.open.side_effect = failure
            with self.assertRaisesRegex(ModelError, '^HTTP_401$'): remote({})
            self.assertEqual(factory.return_value.open.call_count, 1)

    def test_transport_failure_does_not_echo_error_or_retry(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY':'unit-test-placeholder'}), \
             patch('compiler.urllib.request.build_opener') as factory:
            factory.return_value.open.side_effect = urllib.error.URLError('sensitive-detail')
            with self.assertRaisesRegex(ModelError, '^NETWORK_OR_TIMEOUT$'): remote({})
            self.assertEqual(factory.return_value.open.call_count, 1)

    def test_redirect_never_forwards_credentials(self):
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere.invalid'))

    def test_payload_has_no_tools_or_approval(self):
        body = build_request(trace_fixture())
        self.assertEqual(body['text']['format']['type'], 'json_schema')
        self.assertTrue(body['text']['format']['strict'])
        self.assertFalse(body['store'])
        self.assertNotIn('tools', body)

    def test_valid_response(self):
        parsed = parse_response(response())
        self.assertEqual(parsed['draft']['status'], 'candidate')
        self.assertEqual(parsed['input_tokens'], 100)

    def test_incomplete_refusal_wrong_model_and_empty_are_rejected(self):
        refusal = response(); refusal['output'][0]['content'] = [dict(type='refusal', refusal='no')]
        wrong = response(); wrong['model'] = 'different-model'
        empty = response(); empty['output'] = []
        for data in (response(status='incomplete'), refusal, wrong, empty):
            with self.subTest(data=data), self.assertRaises(ModelError): parse_response(data)

    def test_invalid_input_never_calls_network(self):
        network = Mock()
        t = trace_fixture(); t['end'] = 'INTERRUPTED'
        with self.assertRaises(ContractError): compile_trace(t, network)
        network.assert_not_called()

    def test_compile_does_not_grant_approval(self):
        result = compile_trace(trace_fixture(), lambda _: parse_response(response()))
        self.assertEqual(result['review_status'], 'UNREVIEWED')
        self.assertEqual(len(result['skill']['steps']), 2)
        self.assertEqual(result['source'], 'ADB_TEST')

    def test_non_candidate_has_no_skill(self):
        d = dict(status='clarify', reason='Goal does not match evidence.', steps=[])
        result = compile_trace(trace_fixture(), lambda _: parse_response(response(d)))
        self.assertIsNone(result['skill'])

    def test_hallucinated_goal_rejected(self):
        d = draft_fixture(); d['steps'][1]['desired'] = False
        with self.assertRaises(ContractError):
            compile_trace(trace_fixture(), lambda _: parse_response(response(d)))

    def test_no_consent_no_network_no_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'new'; network = Mock()
            with self.assertRaises(ContractError): run_job(trace_fixture(), output, False, network)
            self.assertFalse(output.exists()); network.assert_not_called()

    def test_existing_output_never_overwritten_or_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            network = Mock()
            with self.assertRaises(FileExistsError): run_job(trace_fixture(), Path(tmp), True, network)
            network.assert_not_called()

    def test_failed_model_has_audit_but_no_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'new'
            result = run_job(trace_fixture(), output, True, Mock(side_effect=ModelError('TIMEOUT')))
            self.assertEqual(result['status'], 'FAILED')
            self.assertTrue((output/'audit.json').exists())
            self.assertFalse((output/'skill-v2.json').exists())

    def test_invalid_model_draft_is_retained_for_audit(self):
        d = draft_fixture(); d['steps'][1]['desired'] = False
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'new'
            result = run_job(trace_fixture(), output, True, lambda _: parse_response(response(d)))
            self.assertEqual(result['status'], 'FAILED')
            self.assertTrue((output/'model-response.json').exists())
            self.assertFalse((output/'skill-v2.json').exists())

    def test_job_writes_trace_and_unreviewed_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'new'
            result = run_job(trace_fixture(), output, True, lambda _: parse_response(response()))
            self.assertEqual(result['status'], 'candidate')
            self.assertTrue((output/'trace.json').exists())
            self.assertEqual(json.loads((output/'skill-v2.json').read_text())['schemaVersion'], 2)


if __name__ == '__main__': unittest.main()
