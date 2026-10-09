import json
import unittest
import urllib.error
from unittest.mock import patch
from compiler import ModelError
from jev_selection import remote


class Reply:
    def __init__(self, raw): self.raw = raw
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self, limit): return self.raw[:limit]


class JevTransportTests(unittest.TestCase):
    def send(self, raw):
        with patch('jev_selection.read_credential', return_value='apikey_test'), patch('jev_selection.urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = Reply(raw)
            return remote({'state': 'controlled test'})

    def test_duplicate_keys_are_not_silently_overwritten(self):
        for raw in [b'{"model":"wrong","model":"jev-1.13.0"}',
                    b'{"answers":{"selection":{"choice":"reject","choice":"skill_0"}}}']:
            with self.subTest(raw=raw), self.assertRaises(ModelError): self.send(raw)

    def test_nonfinite_nonobject_and_malformed_fail_closed(self):
        for raw in [b'{"confidence":NaN}', b'[]', b'null', b'broken', b'\xff']:
            with self.subTest(raw=raw), self.assertRaises(ModelError): self.send(raw)

    def test_size_cap_and_unexpected_secret_echo(self):
        with self.assertRaises(ModelError): self.send(b'x' * 65537)
        self.assertEqual(self.send(b'{"echo":"apikey_test"}'), {'echo': '[REDACTED]'})

    def test_http_timeout_and_network_use_only_stable_codes(self):
        for exc, code in [(urllib.error.HTTPError('https://test', 429, 'x', {}, None), 'HTTP_429'),
                          (TimeoutError('private details'), 'NETWORK_OR_TIMEOUT'),
                          (urllib.error.URLError('private details'), 'NETWORK_OR_TIMEOUT')]:
            with patch('jev_selection.read_credential', return_value='apikey_test'), patch('jev_selection.urllib.request.build_opener') as opener:
                opener.return_value.open.side_effect = exc
                with self.assertRaisesRegex(ModelError, '^' + code + '$'): remote({})


if __name__ == '__main__': unittest.main()
