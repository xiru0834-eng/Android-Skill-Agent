"""Fake replies are private protocol fixtures, never GPT learning input/evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from draft_generator import DraftGenerator, Budget, check_draft
from model_api import ModelReply, ModelFailure, OpenAIModel, ModelConfig, UploadGrant
from learning_request import build_request, model_messages
from test_learning_request import material


def request():
    return build_request('学习如何参数化调整灯光亮度，不改电源 / learn parameterized brightness', [material()])


def response(req, *, gap=False):
    sid = req['source_ids'][0]
    if gap:
        return {'status': 'KNOWLEDGE_GAP', 'candidate_flow': None, 'parameter_basis': [], 'step_basis': [],
                'uncertainties': [{'code': 'ENTITY_UNKNOWN', 'source_ids': [sid], 'description': '实体没有证明'}],
                'unsupported_capabilities': [], 'questions': ['请提供公开的实体归属证据']}
    flow = json.loads(Path('D:/Codex-deliveries/smarthome-ui-polish/p1-2-flow-contracts/examples/valid-flow.json').read_text(encoding='utf-8'))
    flow['id'] = 'flow.new_brightness_method'
    flow['evidence_refs'] = [sid]
    return {'status': 'PROPOSED', 'candidate_flow': flow,
            'parameter_basis': [{'parameter': i['name'], 'source_ids': [sid], 'explanation': '协议测试提议，不代表证据证明'} for i in flow['inputs']],
            'step_basis': [{'step_id': s['id'], 'source_ids': [sid], 'explanation': '协议测试提议'} for s in flow['steps']],
            'uncertainties': [{'code': 'ENTITY_UNKNOWN', 'source_ids': [sid], 'description': '未确认业务归属'}],
            'unsupported_capabilities': [], 'questions': ['还需确认实体']}


class Clock:
    def __init__(self): self.now = 0.0
    def __call__(self): return self.now


class FakeModel:
    channel = 'FAKE_MODEL_PROTOCOL_ONLY'
    def __init__(self, replies, hook=None): self.replies, self.calls, self.hook = replies, [], hook
    def generate(self, messages, *, config, timeout_s, max_output_tokens):
        self.calls.append(copy.deepcopy(messages))
        if self.hook: self.hook()
        reply = self.replies.pop(0)
        if isinstance(reply, Exception): raise reply
        return reply


def reply(value):
    return ModelReply(json.dumps(value, ensure_ascii=False), 'stop', None, {'input_tokens': 40, 'output_tokens': 80}, 'test-request')


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.req = request()

    def run_fake(self, replies, budget=None, hook=None, clock=None):
        model = FakeModel(replies, hook)
        generator = DraftGenerator(Path(self.tmp.name), budget or Budget(), clock=clock or Clock(), test_mode=True)
        result = generator.run(self.req, model=model)
        return result, model

    def test_candidate_format_pass_is_never_execution_pass(self):
        out, model = self.run_fake([reply(response(self.req))])
        self.assertEqual(out['status'], 'DRAFT_WITH_KNOWLEDGE_GAPS')
        self.assertFalse(out['execution_authority'])
        self.assertFalse(out['ready_for_device_execution'])
        self.assertEqual(out['candidate_flow']['verified_scope'], [])
        self.assertEqual(out['evidence_channel'], 'FAKE_MODEL_PROTOCOL_ONLY')
        self.assertIn('ENTITY_MAPPING_UNCONFIRMED', out['knowledge_gaps'])
        self.assertNotIn('flow.new_brightness_method', json.dumps(model.calls))

    def test_null_flow_gap_is_accepted_without_inventing_steps(self):
        out, _ = self.run_fake([reply(response(self.req, gap=True))])
        self.assertEqual(out['status'], 'KNOWLEDGE_GAP')
        self.assertIsNone(out['candidate_flow'])

    def test_malformed_output_saved_and_limited_repair(self):
        out, model = self.run_fake([ModelReply('{', 'stop', None, {}, 'bad'), reply(response(self.req, gap=True))])
        self.assertEqual(out['status'], 'KNOWLEDGE_GAP')
        self.assertEqual(out['calls'], 2)
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(out['attempts'][0]['status'], 'DRAFT_FORMAT_ERROR')
        records = list(Path(out['audit_directory']).glob('*response.json'))
        self.assertEqual(len(records), 2)

    def test_persistent_format_failure_does_not_loop(self):
        out, model = self.run_fake([ModelReply('{}', 'stop', None, {}, 'a')] * 3)
        self.assertEqual(out['status'], 'DRAFT_FORMAT_ERROR')
        self.assertEqual(len(model.calls), 2)

    def test_corrective_calls_share_deadline(self):
        clock = Clock()
        def tick(): clock.now += .75
        out, model = self.run_fake([ModelReply('{', 'stop', None, {}, 'a'), reply(response(self.req))],
                                   budget=Budget(total_ms=1000), hook=tick, clock=clock)
        self.assertEqual(out['status'], 'MODEL_TIMEOUT')
        self.assertEqual(len(model.calls), 2)
        self.assertNotIn('candidate_flow', out)

    def test_cancel_after_reply_does_not_resurrect_candidate(self):
        model = FakeModel([reply(response(self.req))])
        gen = DraftGenerator(Path(self.tmp.name), Budget(), test_mode=True)
        model.hook = gen.cancel
        out = gen.run(self.req, model=model)
        self.assertEqual(out['status'], 'CANCELLED')

    def test_session_is_single_use_budget_cannot_reset(self):
        gen = DraftGenerator(Path(self.tmp.name), Budget(), test_mode=True)
        model = FakeModel([reply(response(self.req, gap=True))])
        gen.run(self.req, model=model)
        self.assertEqual(gen.run(self.req, model=model)['status'], 'SESSION_ALREADY_USED')
        self.assertEqual(len(model.calls), 1)

    def test_missing_config_no_network_and_input_receipt_saved(self):
        with patch('socket.socket', side_effect=AssertionError('no-network')):
            out = DraftGenerator(Path(self.tmp.name), Budget()).run(self.req)
        self.assertEqual(out['status'], 'MODEL_CONFIG_MISSING')
        self.assertEqual(out['calls'], 0)
        self.assertTrue((Path(out['audit_directory']) / 'input.json').is_file())

    def test_fake_model_not_allowed_in_normal_entry(self):
        model = FakeModel([reply(response(self.req))])
        out = DraftGenerator(Path(self.tmp.name), Budget()).run(self.req, model=model)
        self.assertEqual(out['status'], 'TEST_MODEL_FORBIDDEN')
        self.assertEqual(model.calls, [])

    def test_model_anomalies_no_automatic_network_retry(self):
        examples = [(ModelFailure('TRANSPORT_ERROR'), 'TRANSPORT_ERROR'),
                    (ModelFailure('MODEL_TIMEOUT'), 'MODEL_TIMEOUT'),
                    (ModelReply('', 'stop', 'refused', {}, 'a'), 'MODEL_REFUSED'),
                    (ModelReply('{}', 'length', None, {}, 'a'), 'MODEL_TRUNCATED'),
                    (ModelReply('{}', 'content_filter', None, {}, 'a'), 'MODEL_REFUSED')]
        for value, expected in examples:
            with self.subTest(expected=expected):
                out, model = self.run_fake([value])
                self.assertEqual(out['status'], expected)
                self.assertEqual(len(model.calls), 1)

    def test_draft_bad_references_unknown_actions_and_authority_blocked(self):
        mutations = []
        a = response(self.req); a['step_basis'][0]['source_ids'] = ['invented']; mutations.append(a)
        a = response(self.req); a['candidate_flow']['steps'][2]['capability'] = 'NewAction'; mutations.append(a)
        a = response(self.req); a['execution_authority'] = True; mutations.append(a)
        a = response(self.req); a['candidate_flow']['verified_scope'] = [{}]; mutations.append(a)
        a = response(self.req); a['parameter_basis'].pop(); mutations.append(a)
        a = response(self.req); a['step_basis'].append(copy.deepcopy(a['step_basis'][0])); mutations.append(a)
        for a in mutations:
            with self.subTest(keys=list(a)):
                out, _ = self.run_fake([reply(a)], Budget(max_calls=1, max_corrections=0))
                self.assertEqual(out['status'], 'DRAFT_FORMAT_ERROR')

    def test_material_gaps_cannot_be_erased_by_model(self):
        a = response(self.req)
        a['uncertainties'] = []
        out, _ = self.run_fake([reply(a)])
        self.assertEqual(out['status'], 'DRAFT_WITH_KNOWLEDGE_GAPS')
        self.assertTrue(out['knowledge_gaps'])

    def test_registered_but_unimplemented_action_is_rejected(self):
        a = response(self.req)
        a['candidate_flow']['dependencies']['capabilities'].append('SetCurtain')
        out, _ = self.run_fake([reply(a)], Budget(max_calls=1, max_corrections=0))
        self.assertEqual(out['status'], 'DRAFT_FORMAT_ERROR')

    def test_secret_in_model_reply_is_redacted_and_rejected(self):
        a = response(self.req)
        a['candidate_flow']['purpose'] = 'sk-' + 'Z' * 50
        out, _ = self.run_fake([reply(a)], Budget(max_calls=1, max_corrections=0))
        self.assertEqual(out['status'], 'MODEL_SECRET_CONTENT')
        records = ''.join(p.read_text(encoding='utf-8') for p in Path(out['audit_directory']).glob('*.json'))
        self.assertNotIn('Z' * 50, records)
        self.assertIn('raw_sha256', records)

    def test_audit_failure_stops_before_model_call(self):
        model = FakeModel([reply(response(self.req))])
        with patch('draft_generator.Audit.save', side_effect=OSError('disk-error')):
            out = DraftGenerator(Path(self.tmp.name), Budget(), test_mode=True).run(self.req, model=model)
        self.assertEqual(out['status'], 'AUDIT_STORAGE_ERROR')
        self.assertEqual(len(model.calls), 0)

    def test_cost_limit_and_upload_mismatch_no_paid_call(self):
        config = ModelConfig('configured-model', 'secret-not-logged', '1', '1', 'verified-rate-source')
        model = OpenAIModel()
        with patch.object(model, 'generate', side_effect=AssertionError('PAID_CALL_FORBIDDEN')):
            out = DraftGenerator(Path(self.tmp.name), Budget()).run(self.req, config=config, model=model)
            self.assertEqual(out['status'], 'UPLOAD_NOT_AUTHORIZED')
            grant = UploadGrant('wrong-digest', self.req['environment'])
            out = DraftGenerator(Path(self.tmp.name), Budget()).run(self.req, config=config, model=model, grant=grant)
            self.assertEqual(out['status'], 'UPLOAD_NOT_AUTHORIZED')
            grant = UploadGrant(self.req['input_digest'], self.req['environment'])
            out = DraftGenerator(Path(self.tmp.name), Budget(max_cost_usd='0.000001')).run(self.req, config=config, model=model, grant=grant)
            self.assertEqual(out['status'], 'COST_BUDGET_EXCEEDED')
            self.assertEqual(out['calls'], 0)

    def test_invalid_budget_and_duplicate_json_are_rejected(self):
        for args in ({'max_calls': 0}, {'total_ms': 0}, {'max_corrections': 3, 'max_calls': 2}, {'max_cost_usd': '-1'}, {'max_calls': True}):
            with self.subTest(args=args), self.assertRaises(ValueError): Budget(**args)
        out, _ = self.run_fake([ModelReply('{"status":"PROPOSED","status":"KNOWLEDGE_GAP"}', 'stop', None, {}, 'a')], Budget(max_calls=1, max_corrections=0))
        self.assertEqual(out['status'], 'DRAFT_FORMAT_ERROR')

    def test_request_tampering_rejected_before_model(self):
        bad = copy.deepcopy(self.req); bad['goal'] = 'changed'
        model = FakeModel([reply(response(self.req))])
        out = DraftGenerator(Path(self.tmp.name), Budget(), test_mode=True).run(bad, model=model)
        self.assertEqual(out['status'], 'INPUT_INTEGRITY_ERROR')
        self.assertEqual(model.calls, [])

    def test_existing_capabilities_can_be_composed_with_new_flow_name(self):
        a = response(self.req)
        flow = a['candidate_flow']
        flow['inputs'].append({'name': 'state', 'type': 'enum', 'choices': ['off', 'on'],
                               'unit': 'enum', 'default_rule': 'REQUIRE_EXPLICIT'})
        flow['must_preserve'] = []
        flow['allowed_effects'].append({'entity_input': 'light', 'property': 'power'})
        flow['steps'].insert(2, {'id': 'set_power', 'op': 'call', 'capability': 'SetPower',
                                 'entity_input': 'light', 'argument': {'kind': 'input', 'name': 'state'}})
        sid = self.req['source_ids'][0]
        a['parameter_basis'].append({'parameter': 'state', 'source_ids': [sid], 'explanation': 'Protocol fixture'})
        a['step_basis'].append({'step_id': 'set_power', 'source_ids': [sid], 'explanation': 'Protocol fixture'})
        out, _ = self.run_fake([reply(a)])
        self.assertEqual(out['checks']['p1_static_check']['call_count'], 2)
        self.assertEqual(out['status'], 'DRAFT_WITH_KNOWLEDGE_GAPS')
        self.assertFalse(out['ready_for_device_execution'])

    def test_concurrent_session_cannot_acquire_second_budget(self):
        gen = DraftGenerator(Path(self.tmp.name), Budget(), test_mode=True)
        gen.lock.acquire()
        try:
            self.assertEqual(gen.run(self.req)['status'], 'SESSION_BUSY')
        finally:
            gen.lock.release()

    def test_model_response_size_limit_is_explicit(self):
        out, model = self.run_fake([ModelReply('x' * 65537, 'stop', None, {}, 'a')])
        self.assertEqual(out['status'], 'MODEL_RESPONSE_TOO_LARGE')
        self.assertEqual(len(model.calls), 1)

    def test_audit_postreply_failure_never_returns_valid_candidate(self):
        from draft_generator import Audit
        original = Audit.save
        def fail_check(audit, name, value):
            if name.endswith('-check.json'): raise OSError('disk-error')
            return original(audit, name, value)
        with patch('draft_generator.Audit.save', fail_check):
            out, _ = self.run_fake([reply(response(self.req))])
        self.assertEqual(out['status'], 'AUDIT_STORAGE_ERROR')
        self.assertNotIn('candidate_flow', out)

    def test_price_reservation_is_shared_across_corrections(self):
        # Mock HTTP boundary only; this is not a real paid call or GPT quality result.
        from decimal import Decimal
        config = ModelConfig('explicit-model', 'test-secret', '1', '1', 'rate-source')
        messages = model_messages(self.req)
        first = (4 * (len(json.dumps(messages, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()) + 4096) + 4096) / Decimal(1000000)
        budget = Budget(max_cost_usd=str(first + Decimal('0.0000001')))
        model = OpenAIModel()
        with patch.object(model, 'generate', return_value=ModelReply('{', 'stop', None, {}, 'a')) as call:
            out = DraftGenerator(Path(self.tmp.name), budget).run(self.req, config=config, model=model,
                grant=UploadGrant(self.req['input_digest'], self.req['environment']))
        self.assertEqual(out['status'], 'COST_BUDGET_EXCEEDED')
        self.assertEqual(call.call_count, 1)
        self.assertEqual(out['calls'], 1)

    def test_contract_only_inputs_cannot_include_private_answer_with_recomputed_hash(self):
        from p31deps import digest
        bad = copy.deepcopy(self.req)
        bad['material']['oracle'] = {'expected': 60}
        bad['input_digest'] = digest({k: v for k, v in bad.items() if k not in ('input_digest', 'request_id')})
        model = FakeModel([reply(response(self.req))])
        out = DraftGenerator(Path(self.tmp.name), Budget(), test_mode=True).run(bad, model=model)
        self.assertEqual(out['status'], 'PRIVATE_INPUT_FORBIDDEN')
        self.assertEqual(model.calls, [])


if __name__ == '__main__': unittest.main()
