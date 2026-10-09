import json
import unittest
from unittest.mock import patch
from model_api import ModelConfig, ModelFailure, OpenAIModel


class HTTPResponse:
    def __init__(self, value=None, *, status=200, raw=None):
        self.status = status
        self.raw = raw if raw is not None else json.dumps(value).encode()
    def read1(self, n):
        chunk, self.raw = self.raw[:n], self.raw[n:]
        return chunk
    def getheader(self, name): return 'mock-http-id'


class Connection:
    def __init__(self, response): self.response, self.requests, self.closed, self.sock = response, [], False, None
    def request(self, *args, **kwargs): self.requests.append((args, kwargs))
    def getresponse(self): return self.response
    def close(self): self.closed = True


def body(**message):
    return {'choices': [{'finish_reason': 'stop', 'message': {'content': '{}', **message}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20}}


class TransportTests(unittest.TestCase):
    def generate(self, response):
        conn = Connection(response)
        with patch('model_api.http.client.HTTPSConnection', return_value=conn) as factory:
            result = OpenAIModel().generate([{'role': 'user', 'content': 'JSON'}],
                config=ModelConfig('explicit-model', 'test-secret', '1', '2', 'rate-source'), timeout_s=2, max_output_tokens=100)
        return result, conn, factory

    def test_mock_http_contract_fixed_host_no_tools(self):
        result, conn, factory = self.generate(HTTPResponse(body()))
        self.assertEqual(factory.call_args.args, ('api.openai.com',))
        self.assertEqual(conn.requests[0][0], ('POST', '/v1/chat/completions'))
        payload = json.loads(conn.requests[0][1]['body'])
        self.assertNotIn('tools', payload)
        self.assertFalse(payload['store'])
        self.assertEqual(payload['max_completion_tokens'], 100)
        self.assertEqual(result.text, '{}')
        self.assertTrue(conn.closed)

    def test_redirects_and_http_failures_not_followed(self):
        for code in (302, 401, 429, 500):
            with self.subTest(code=code), self.assertRaises(ModelFailure) as cm:
                self.generate(HTTPResponse({}, status=code))
            self.assertEqual(cm.exception.code, 'MODEL_HTTP_' + str(code))

    def test_function_or_tool_output_cannot_be_dispatched(self):
        with self.assertRaises(ModelFailure) as cm:
            self.generate(HTTPResponse(body(tool_calls=[{'name': 'click'}])))
        self.assertEqual(cm.exception.code, 'MODEL_TOOL_CALL_FORBIDDEN')

    def test_oversize_response_is_bounded(self):
        with self.assertRaises(ModelFailure) as cm:
            self.generate(HTTPResponse(raw=b'x' * 65537))
        self.assertEqual(cm.exception.code, 'MODEL_RESPONSE_TOO_LARGE')

    def test_malformed_http_payload_has_safe_failure(self):
        for value in (None, {}, {'choices': []}, body(content=['not text'])):
            with self.subTest(value=value), self.assertRaises(ModelFailure):
                self.generate(HTTPResponse(value))

    def test_missing_invalid_price_or_key_configuration_rejected(self):
        examples = [ModelConfig('', 'secret', '1', '2', 'source'), ModelConfig('model', '', '1', '2', 'source'),
                    ModelConfig('model', 'secret', 'NaN', '2', 'source'), ModelConfig('model', 'secret', '1', '-1', 'source'),
                    ModelConfig('model', 'secret', '1', '2', '')]
        for value in examples:
            with self.subTest(model=value.model), self.assertRaises(ModelFailure): value.validate()

    def test_configuration_repr_never_contains_key(self):
        config = ModelConfig('model', 'do-not-print-this-key', '1', '2', 'source')
        self.assertNotIn('do-not-print-this-key', repr(config))
        self.assertNotIn('do-not-print-this-key', json.dumps(config.public()))


if __name__ == '__main__': unittest.main()
