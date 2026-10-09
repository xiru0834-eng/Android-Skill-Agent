"""Wire text contract matching Android ParameterText after local normalization; no API calls."""
import json
import unittest
from parameter_calls import build_request
from test_parameter_calls import CATALOG


class ParameterTextContractTests(unittest.TestCase):
    def test_ascii_and_chinese_utf16_boundary(self):
        for unit in ('a', '灯'):
            with self.subTest(unit=unit):
                raw=unit*240
                request=build_request(raw,CATALOG)
                self.assertEqual(json.loads(request['input'][1]['content'])['text'],raw)
                with self.assertRaises(ValueError):build_request(unit*241,CATALOG)

    def test_supplementary_character_boundary_matches_java_units(self):
        accepted='😀'*120
        request=build_request(accepted,CATALOG)
        self.assertEqual(json.loads(request['input'][1]['content'])['text'],accepted)
        with self.assertRaises(ValueError):build_request('😀'*121,CATALOG)

    def test_internal_controls_rejected(self):
        for control in ('\n','\r','\t','\0'):
            with self.subTest(control=repr(control)),self.assertRaises(ValueError):
                build_request('light'+control+'on',CATALOG)

    def test_native_trimmed_text_accepted_and_preserved(self):
        for raw in ('  Set bedroom light to 80 percent  ','  把卧室灯调到80%  '):
            # Android sends the canonical text; its raw snapshot stays local.
            request=build_request(raw.strip(),CATALOG)
            self.assertEqual(json.loads(request['input'][1]['content'])['text'],raw.strip())

    def test_blank_and_lone_surrogates_do_not_form_request(self):
        for raw in ('',' ','　','\ud800','\udc00'):
            with self.subTest(raw=repr(raw)),self.assertRaises((ValueError,UnicodeEncodeError)):
                build_request(raw,CATALOG)


if __name__=='__main__':unittest.main()
