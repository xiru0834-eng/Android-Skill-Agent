import unittest
from intent import build_request, validate_intent, understand


class IntentTests(unittest.TestCase):
    def payload(self, **changes):
        value = dict(status='invoke', skill_id='room_controls', lamp=True, fan=False, message='OK')
        value.update(changes)
        return value

    def test_both_languages_preserved(self):
        for text in ('打开阅读灯，关闭风扇', 'Turn on the reading lamp and turn off the fan'):
            self.assertIn(text, build_request(text)['input'][1]['content'])

    def test_partial_target_is_not_invented(self):
        self.assertIsNone(validate_intent(self.payload(fan=None))['fan'])

    def test_reject_invalid_model_data(self):
        for changes in (dict(lamp='true'), dict(lamp=1), dict(skill_id='other'),
                        dict(lamp=None, fan=None), dict(status='clarify'), dict(extra='command')):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_intent(self.payload(**changes))

    def test_clarification_has_no_actions(self):
        self.assertEqual(validate_intent(self.payload(status='clarify', lamp=None, fan=None))['status'], 'clarify')

    def test_empty_and_long_input_rejected_before_model(self):
        for text in ('', ' ', 'a'*501, None):
            with self.assertRaises(ValueError): build_request(text)

    def test_model_transport_injected_and_validated(self):
        result = understand('打开灯', lambda body: dict(draft=self.payload(fan=None)))
        self.assertTrue(result['lamp'])
        with self.assertRaises(ValueError):
            understand('开灯', lambda body: dict(draft=self.payload(lamp='yes')))


if __name__ == '__main__': unittest.main()
