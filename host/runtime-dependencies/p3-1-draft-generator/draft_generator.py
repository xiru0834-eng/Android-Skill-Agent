"""Inert proposals with actual P1 static checking, bounded learning and append-only receipts."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import copy
import hashlib
import json
from pathlib import Path
import re
import threading
import time
import uuid

from learning_request import model_messages, MAX_INPUT_BYTES, guard, RequestError
from model_api import ModelConfig, ModelFailure, OpenAIModel, UploadGrant
from p31deps import canonical, contracts, digest, bundle_contract

ENVELOPE_KEYS = {'status', 'candidate_flow', 'parameter_basis', 'step_basis', 'uncertainties', 'unsupported_capabilities', 'questions'}
SECRET = re.compile(r'(?i)\bsk-[A-Za-z0-9_-]{12,}|\bBearer\s+[^\s"\\]+|"(?:api_key|password|secret|credential|authorization)"\s*:\s*"[^"\n]+"')


def redacted(text):
    return SECRET.sub('[REDACTED_SECRET]', text)


def need(condition, code):
    if not condition:
        raise ModelFailure(code)


@dataclass(frozen=True)
class Budget:
    max_calls: int = 2
    max_corrections: int = 1
    total_ms: int = 30000
    max_output_tokens: int = 4096
    max_cost_usd: str = '0.10'

    def __post_init__(self):
        limits = ((self.max_calls, 1, 20), (self.max_corrections, 0, 19),
                  (self.total_ms, 1, 120000), (self.max_output_tokens, 1, 8192))
        if any(type(n) is not int or not low <= n <= high for n, low, high in limits) or self.max_corrections >= self.max_calls:
            raise ValueError('INVALID_LEARNING_BUDGET')
        try:
            price = Decimal(self.max_cost_usd)
            if not price.is_finite() or price < 0:
                raise ValueError('INVALID_COST_BUDGET')
        except (InvalidOperation, TypeError):
            raise ValueError('INVALID_COST_BUDGET') from None


class Audit:
    def __init__(self, root):
        self.directory = Path(root) / str(uuid.uuid4())
        self.directory.mkdir(parents=True, exist_ok=False)

    def save(self, filename, value):
        # Only internal literal filenames; never a candidate-provided name or path.
        with (self.directory / filename).open('x', encoding='utf-8') as f:
            f.write(canonical(value))


def check_draft(raw, request):
    need(type(raw) is str and len(raw.encode()) <= 65536, 'DRAFT_SIZE_LIMIT')
    need(not SECRET.search(raw), 'MODEL_SECRET_CONTENT')
    try:
        value = contracts.parse_document(raw.encode())
        need(type(value) is dict and set(value) == ENVELOPE_KEYS, 'DRAFT_ENVELOPE_INVALID')
        need(value['status'] in ('PROPOSED', 'KNOWLEDGE_GAP'), 'DRAFT_STATUS_INVALID')
        for field in ('parameter_basis', 'step_basis', 'uncertainties', 'unsupported_capabilities', 'questions'):
            need(type(value[field]) is list and len(value[field]) <= 128, 'DRAFT_FIELD_INVALID')
        known = set(request['source_ids'])

        def refs(items):
            need(type(items) is list and items and len(items) == len(set(items)), 'DRAFT_REFERENCE_INVALID')
            need(all(type(s) is str and s in known for s in items), 'DRAFT_REFERENCE_INVALID')

        for item in value['uncertainties']:
            need(type(item) is dict and set(item) == {'code', 'source_ids', 'description'}, 'DRAFT_UNCERTAINTY_INVALID')
            need(type(item['code']) is str and 1 <= len(item['code']) <= 128, 'DRAFT_UNCERTAINTY_INVALID')
            need(type(item['description']) is str and 1 <= len(item['description']) <= 2000, 'DRAFT_UNCERTAINTY_INVALID')
            if item['source_ids']:
                refs(item['source_ids'])
            else:
                need(item['source_ids'] == [], 'DRAFT_REFERENCE_INVALID')
        for field in ('questions', 'unsupported_capabilities'):
            need(all(type(t) is str and 1 <= len(t) <= 2000 for t in value[field]), 'DRAFT_FIELD_INVALID')
        flow = value['candidate_flow']
        if flow is None:
            need(value['status'] == 'KNOWLEDGE_GAP' and value['uncertainties'] and value['questions'], 'EMPTY_DRAFT_UNEXPLAINED')
            need(not value['parameter_basis'] and not value['step_basis'], 'EMPTY_DRAFT_WITH_STEPS')
            check = {'status': 'NO_FLOW_TO_CHECK', 'validation_scope': 'EXPLICIT_KNOWLEDGE_GAP'}
        else:
            need(value['status'] == 'PROPOSED', 'DRAFT_STATUS_INVALID')
            check = contracts.validate_document(flow)
            need(flow['kind'] == 'FlowSkill' and flow['verified_scope'] == [], 'DRAFT_VERIFIED_SCOPE_FORBIDDEN')
            allowed = {c['name'] for c in request['allowed_capabilities']['definitions']}
            need(set(flow['dependencies']['capabilities']) <= allowed, 'UNSUPPORTED_CAPABILITY')
            need(all(set(i.get('required_capabilities', [])) <= allowed for i in flow['inputs']), 'UNSUPPORTED_CAPABILITY')
            refs(flow['evidence_refs'])
            for field, id_field, expected in (
                ('parameter_basis', 'parameter', {i['name'] for i in flow['inputs']}),
                ('step_basis', 'step_id', {s['id'] for s in flow['steps']})):
                rows = value[field]
                need(all(type(r) is dict and set(r) == {id_field, 'source_ids', 'explanation'} for r in rows), 'DRAFT_BASIS_INVALID')
                need(all(type(r[id_field]) is str for r in rows), 'DRAFT_BASIS_INVALID')
                need(len(rows) == len(expected) and {r[id_field] for r in rows} == expected, 'DRAFT_BASIS_INCOMPLETE')
                for row in rows:
                    refs(row['source_ids'])
                    need(type(row['explanation']) is str and 1 <= len(row['explanation']) <= 2000, 'DRAFT_BASIS_INVALID')
        # Metadata remains proposal, never factual validation or authorisation.
        safe = bundle_contract.sanitize_fragment(value)
        return safe, {'p1_static_check': check, 'evidence_check': 'REFERENCES_EXIST_ONLY_NOT_CLAIM_TRUTH',
                      'full_flow_compile': 'NOT_EVALUATED_NO_TASK_OR_AUTHORIZED_BINDING',
                      'business_execution': 'NOT_TESTED', 'execution_authority': False}
    except contracts.ContractError as exc:
        raise ModelFailure('DRAFT_FORMAT_ERROR') from exc
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, ModelFailure):
            raise
        raise ModelFailure('DRAFT_FORMAT_ERROR') from None


class DraftGenerator:
    def __init__(self, audit_root, budget, *, clock=time.monotonic, test_mode=False):
        self.audit_root, self.budget, self.clock, self.test_mode = audit_root, budget, clock, test_mode
        self.used = False
        self.cancelled = threading.Event()
        self.lock = threading.Lock()

    def cancel(self):
        self.cancelled.set()

    def run(self, request, *, model=None, config=None, grant=None):
        if not self.lock.acquire(blocking=False):
            return {'status': 'SESSION_BUSY', 'execution_authority': False}
        try:
            if self.used:
                return {'status': 'SESSION_ALREADY_USED', 'execution_authority': False}
            self.used = True
            return self._run(copy.deepcopy(request), model=model, config=config, grant=grant)
        finally:
            self.lock.release()

    def _run(self, request, *, model, config, grant):
        started = self.clock()
        deadline = started + self.budget.total_ms / 1000
        result = {'status': 'UNCONFIRMED', 'execution_authority': False, 'ready_for_device_execution': False,
                  'calls': 0, 'reserved_cost_usd': '0', 'attempts': [], 'candidate_lifecycle': 'DRAFT_ONLY',
                  'evidence_channel': 'NO_MODEL_CALL', 'knowledge_gaps': request.get('knowledge_gaps', [])}
        audit = None
        try:
            audit = Audit(self.audit_root)
            result['audit_directory'] = str(audit.directory)
            need(request.get('kind') == 'LearningRequest', 'INPUT_INTEGRITY_ERROR')
            core = {k: v for k, v in request.items() if k not in ('input_digest', 'request_id')}
            need(request.get('input_digest') == digest(core) and request.get('execution_authority') is False
                 and request.get('model_upload_authorized') is False, 'INPUT_INTEGRITY_ERROR')
            guard(request)
            messages = model_messages(request)
            audit.save('input.json', request)
            audit.save('constructed-messages.json', messages)
            public_config = config.public() if isinstance(config, ModelConfig) else None
            audit.save('config.json', {'config': public_config, 'budget': self.budget.__dict__,
                                      'upload_grant': {'input_digest': grant.input_digest, 'environment': grant.environment}
                                      if isinstance(grant, UploadGrant) else None})
            fake = getattr(model, 'channel', None) == 'FAKE_MODEL_PROTOCOL_ONLY'
            if fake:
                need(self.test_mode, 'TEST_MODEL_FORBIDDEN')
            else:
                need(isinstance(config, ModelConfig), 'MODEL_CONFIG_MISSING')
                config.validate()
                need(isinstance(grant, UploadGrant) and grant.input_digest == request['input_digest']
                     and grant.environment == request['environment'], 'UPLOAD_NOT_AUTHORIZED')
                model = model or OpenAIModel()
                need(isinstance(model, OpenAIModel), 'MODEL_TRANSPORT_NOT_ALLOWED')
            corrections = 0
            cost = Decimal('0')
            while True:
                need(not self.cancelled.is_set(), 'CANCELLED')
                remaining = deadline - self.clock()
                need(remaining > 0, 'MODEL_TIMEOUT')
                need(result['calls'] < self.budget.max_calls, 'CALL_BUDGET_EXCEEDED')
                payload_bytes = len(canonical(messages).encode())
                need(payload_bytes <= MAX_INPUT_BYTES, 'INPUT_BYTES_LIMIT')
                if not fake:
                    # Conservative token reservation, not a claim about final account charges.
                    input_rate, output_rate = config.validate()
                    input_bound = 4 * (payload_bytes + 4096)
                    reserve = (input_bound * input_rate + self.budget.max_output_tokens * output_rate) / Decimal(1000000)
                    need(cost + reserve <= Decimal(self.budget.max_cost_usd), 'COST_BUDGET_EXCEEDED')
                    cost += reserve  # Failed/timeout calls are not refunded by this local ledger.
                number = result['calls'] + 1
                audit.save(f'{number:02d}-request.json', {'messages': messages, 'remaining_ms': remaining * 1000,
                            'max_completion_tokens': self.budget.max_output_tokens, 'reserved_cost_usd': str(cost)})
                result['calls'] = number
                result['reserved_cost_usd'] = str(cost)
                result['evidence_channel'] = model.channel
                try:
                    reply = model.generate(messages, config=config, timeout_s=remaining,
                                           max_output_tokens=self.budget.max_output_tokens)
                    need(type(reply.text) is str and len(reply.text.encode()) <= 65536, 'MODEL_RESPONSE_TOO_LARGE')
                    audit.save(f'{number:02d}-response.json', {'raw_redacted': redacted(reply.text),
                               'raw_sha256': hashlib.sha256(reply.text.encode()).hexdigest(),
                               'redaction_applied': redacted(reply.text) != reply.text,
                               'finish_reason': reply.finish_reason, 'refusal': bool(reply.refusal),
                               'request_id': redacted(reply.request_id or ''), 'usage': reply.usage})
                    need(not self.cancelled.is_set(), 'CANCELLED')
                    need(self.clock() < deadline, 'MODEL_TIMEOUT')
                    need(not reply.refusal and reply.finish_reason != 'content_filter', 'MODEL_REFUSED')
                    need(reply.finish_reason != 'length', 'MODEL_TRUNCATED')
                    need(reply.finish_reason == 'stop', 'MODEL_PROTOCOL_ERROR')
                    draft, check = check_draft(reply.text, request)
                    status = 'KNOWLEDGE_GAP' if draft['candidate_flow'] is None else (
                        'DRAFT_WITH_KNOWLEDGE_GAPS' if request['knowledge_gaps'] or draft['uncertainties'] else 'DRAFT_ONLY')
                    result.update(status=status, **{k: v for k, v in draft.items() if k != 'status'}, checks=check)
                    result['attempts'].append({'attempt': number, 'status': status})
                    audit.save(f'{number:02d}-check.json', check)
                    break
                except ModelFailure as exc:
                    raw_code = exc.code
                    format_codes = {'DRAFT_FORMAT_ERROR', 'DRAFT_ENVELOPE_INVALID', 'DRAFT_STATUS_INVALID',
                                    'DRAFT_FIELD_INVALID', 'DRAFT_REFERENCE_INVALID', 'DRAFT_UNCERTAINTY_INVALID',
                                    'EMPTY_DRAFT_UNEXPLAINED', 'EMPTY_DRAFT_WITH_STEPS', 'DRAFT_VERIFIED_SCOPE_FORBIDDEN',
                                    'UNSUPPORTED_CAPABILITY', 'DRAFT_BASIS_INVALID', 'DRAFT_BASIS_INCOMPLETE', 'DRAFT_SIZE_LIMIT'}
                    status = 'DRAFT_FORMAT_ERROR' if raw_code in format_codes else raw_code
                    result['attempts'].append({'attempt': number, 'status': status, 'diagnostic': raw_code})
                    audit.save(f'{number:02d}-error.json', result['attempts'][-1])
                    if status != 'DRAFT_FORMAT_ERROR' or corrections >= self.budget.max_corrections or number >= self.budget.max_calls:
                        raise ModelFailure(status) from None
                    corrections += 1
                    # No golden Flow, formal answer, or old raw output echoed into correction.
                    messages = model_messages(request) + [{'role': 'user', 'content': canonical({
                        'correction': corrections, 'diagnostic': raw_code,
                        'rule': 'Return corrected JSON using original public evidence only; a knowledge gap is acceptable.'})}]
        except ModelFailure as exc:
            result['status'] = exc.code
        except RequestError as exc:
            result['status'] = exc.code
        except OSError:
            result['status'] = 'AUDIT_STORAGE_ERROR'
            result.pop('candidate_flow', None)
        except (ValueError, TypeError, KeyError):
            result['status'] = 'INPUT_CONTRACT_ERROR'
        result['elapsed_ms'] = max(0, (self.clock() - started) * 1000)
        if audit:
            try:
                audit.save('result.json', result)
            except OSError:
                result['status'] = 'AUDIT_STORAGE_ERROR'
                result.pop('candidate_flow', None)
        return result
