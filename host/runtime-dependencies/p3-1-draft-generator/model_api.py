"""Explicit optional OpenAI transport. No key discovery, redirects, tools or HTTP retries."""
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import http.client
import json
import re
import socket
import time


class ModelFailure(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ModelReply:
    text: str
    finish_reason: str
    refusal: str | None
    usage: dict
    request_id: str | None


@dataclass(frozen=True)
class UploadGrant:
    """Host-only explicit grant; a Bundle/model proposal cannot create this authority."""
    input_digest: str
    environment: dict


@dataclass(frozen=True)
class ModelConfig:
    model: str
    api_key: str = field(repr=False)
    input_usd_per_million: str
    output_usd_per_million: str
    verified_rate_source: str

    def public(self):
        value = {'model': self.model, 'endpoint': 'https://api.openai.com/v1/chat/completions',
                'input_usd_per_million': self.input_usd_per_million,
                'output_usd_per_million': self.output_usd_per_million,
                'verified_rate_source': self.verified_rate_source, 'store': False,
                'http_retries': 0, 'tools': [], 'response_format': 'json_object'}
        # Even a misconfigured descriptive field must not copy the actual key into audit.
        return {k: v.replace(self.api_key, '[REDACTED_KEY]')
                if type(v) is str and self.api_key else v for k, v in value.items()}

    def validate(self):
        if type(self.model) is not str or not re.fullmatch('[A-Za-z0-9_.:-]{1,128}', self.model):
            raise ModelFailure('MODEL_CONFIG_INVALID')
        if type(self.api_key) is not str or not self.api_key or '\n' in self.api_key or '\r' in self.api_key:
            raise ModelFailure('MODEL_CONFIG_INVALID')
        if type(self.verified_rate_source) is not str or not self.verified_rate_source:
            raise ModelFailure('PRICE_CONFIG_MISSING')
        try:
            prices = [Decimal(v) for v in (self.input_usd_per_million, self.output_usd_per_million)]
        except (InvalidOperation, TypeError, ValueError):
            raise ModelFailure('PRICE_CONFIG_INVALID') from None
        if any(not p.is_finite() or p <= 0 for p in prices):
            raise ModelFailure('PRICE_CONFIG_INVALID')
        return prices


class OpenAIModel:
    channel = 'REAL_OPENAI_API'

    def generate(self, messages, *, config, timeout_s, max_output_tokens):
        config.validate()
        if timeout_s <= 0:
            raise ModelFailure('MODEL_TIMEOUT')
        data = {'model': config.model, 'messages': messages, 'store': False,
                'response_format': {'type': 'json_object'}, 'max_completion_tokens': max_output_tokens}
        body = json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
        deadline = time.monotonic() + timeout_s
        conn = http.client.HTTPSConnection('api.openai.com', timeout=timeout_s)
        try:
            conn.request('POST', '/v1/chat/completions', body=body,
                         headers={'Content-Type': 'application/json', 'Authorization': 'Bearer ' + config.api_key})
            response = conn.getresponse()
            if not 200 <= response.status < 300:
                # Do not propagate response bodies, keys or attacker-controlled error strings.
                raise ModelFailure('MODEL_HTTP_' + str(response.status))
            chunks, total = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ModelFailure('MODEL_TIMEOUT')
                if conn.sock is not None:
                    conn.sock.settimeout(remaining)
                chunk = response.read1(min(8192, 65537 - total))
                total += len(chunk)
                if total > 65536:
                    raise ModelFailure('MODEL_RESPONSE_TOO_LARGE')
                if not chunk:
                    break
                chunks.append(chunk)
            value = json.loads(b''.join(chunks))
            choices = value['choices']
            if len(choices) != 1:
                raise ModelFailure('MODEL_PROTOCOL_ERROR')
            choice = choices[0]
            message = choice['message']
            if message.get('tool_calls') or message.get('function_call'):
                raise ModelFailure('MODEL_TOOL_CALL_FORBIDDEN')
            usage = value.get('usage', {})
            safe_usage = {k: usage[k] for k in ('prompt_tokens', 'completion_tokens', 'total_tokens')
                          if type(usage.get(k)) is int and usage[k] >= 0}
            content = message.get('content')
            if content is not None and type(content) is not str:
                raise ModelFailure('MODEL_PROTOCOL_ERROR')
            refusal = message.get('refusal')
            if refusal is not None and type(refusal) is not str:
                raise ModelFailure('MODEL_PROTOCOL_ERROR')
            return ModelReply(content or '', choice['finish_reason'], refusal, safe_usage,
                              response.getheader('x-request-id'))
        except ModelFailure:
            raise
        except (TimeoutError, socket.timeout):
            raise ModelFailure('MODEL_TIMEOUT') from None
        except (OSError, http.client.HTTPException):
            raise ModelFailure('TRANSPORT_ERROR') from None
        except (ValueError, KeyError, TypeError, UnicodeError):
            raise ModelFailure('MODEL_PROTOCOL_ERROR') from None
        finally:
            conn.close()
