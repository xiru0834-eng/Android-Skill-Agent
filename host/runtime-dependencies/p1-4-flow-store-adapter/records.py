"""Trusted in-process records. JSON/model output cannot instantiate authority.

This is an application trust boundary, not a sandbox against malicious Python
plugins or administrators able to replace code/database files.
"""
from dataclasses import dataclass
import json
from p14deps import canonical

_ISSUER = object()


class RunEvidence:
    def __init__(self, body, *, issuer=None):
        if issuer is not _ISSUER:
            raise ValueError('TRUSTED_ADAPTER_EVIDENCE_REQUIRED')
        self._json = canonical(body)

    def to_dict(self):
        return json.loads(self._json)


def _issue_evidence(body):
    return RunEvidence(body, issuer=_ISSUER)


@dataclass(frozen=True)
class ValidationAuthority:
    version_key: str
    operator_id: str
    confirmed: bool


@dataclass(frozen=True)
class PublishAuthority:
    version_key: str
    operator_id: str
    environment_hash: str
    evidence_channel: str
    confirmed: bool
