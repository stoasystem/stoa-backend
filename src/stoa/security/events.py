"""Allowlisted security telemetry projection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SecurityEvent:
    actor_id: str
    canonical_role: str
    resource_type: str
    action: str
    purpose: str
    policy_version: str
    result_code: str
    correlation_id: str
    evidence_reference: str | None = None


_EVENT_KEYS = frozenset(SecurityEvent.__dataclass_fields__)


def project_security_event(event: SecurityEvent | Mapping[str, Any]) -> dict[str, Any]:
    """Build telemetry solely from named safe fields, dropping every extra input."""
    source = asdict(event) if isinstance(event, SecurityEvent) else event
    return {key: source[key] for key in _EVENT_KEYS if key in source and source[key] is not None}


def contains_canary(projected: Mapping[str, Any], canaries: tuple[str, ...]) -> bool:
    rendered = repr(dict(projected))
    return any(canary and canary in rendered for canary in canaries)
