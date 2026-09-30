"""#48 decision 1: an administrator may not grant a capability to itself.

The refusal is recorded before it is returned, as the self-deactivation and
peer-password refusals are. The way out for a lone administrator is the offline
operator script, in the AWS trust domain; see test_operator_capability.py.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
import pytest

from stoa.db.repositories import capability_repo
from stoa.services import privileged_identity_service


MANAGER = {
    "user_id": "admin-1",
    "role": "admin",
    "account_status": "active",
    "capabilities": {capability_repo.ADMIN_IDENTITY_MANAGER: True},
}
GRANT = {
    "command_id": "command-1",
    "grant_id": "grant-1",
    "capability": capability_repo.TEACHER_SUPPORT_ALLOWANCE_MANAGER,
    "scope": "global",
    "effective_at": "2026-09-30T12:00:00Z",
    "expected_generation": 0,
}


@pytest.fixture
def stores(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    recorded: dict[str, list[Any]] = {"grants": [], "audits": []}

    def grant_capability(**kwargs: Any) -> dict[str, Any]:
        recorded["grants"].append(kwargs)
        return {
            "grant_id": kwargs["grant_id"],
            "user_id": kwargs["user_id"],
            "capability": kwargs["capability"],
            "scope": kwargs["scope"],
            "status": "active",
            "version": 1,
            "generation": 1,
            "effective_at": kwargs["effective_at"],
        }

    monkeypatch.setattr(
        privileged_identity_service.capability_repo, "grant_capability", grant_capability
    )
    monkeypatch.setattr(
        privileged_identity_service.security_audit_repo,
        "append_event",
        lambda stream_id, event: recorded["audits"].append((stream_id, dict(event))),
    )
    return recorded


def _grant(actor: dict[str, Any], target_id: str) -> dict[str, Any]:
    return privileged_identity_service.grant_capability(
        actor=actor, target_id=target_id, reason="approved change", **GRANT
    )


def test_a_self_grant_is_refused_and_writes_no_grant(stores: dict[str, list[Any]]) -> None:
    with pytest.raises(HTTPException) as refused:
        _grant(MANAGER, "admin-1")
    assert refused.value.status_code == 409
    assert refused.value.detail == {"code": "capability_self_grant_forbidden"}
    assert stores["grants"] == []


def test_the_refusal_is_recorded_before_it_is_returned(stores: dict[str, list[Any]]) -> None:
    with pytest.raises(HTTPException):
        _grant(MANAGER, "admin-1")
    [(stream_id, event)] = stores["audits"]
    assert stream_id == "admin-1"
    assert event["event_type"] == "capability_grant_denied"
    assert event["actor_id"] == event["target_id"] == "admin-1"
    assert event["target_type"] == "capability_grant"
    assert event["action"] == "grant_capability"
    assert event["reason_code"] == "capability_self_grant_forbidden"
    assert event["command_id"] == "command-1"
    # Shaped like the account refusals: `<kind>_denied:<reason>`, then what was asked for.
    assert event["evidence_reference"] == (
        "capability_grant_denied:capability_self_grant_forbidden:"
        f"{capability_repo.TEACHER_SUPPORT_ALLOWANCE_MANAGER}"
    )
    assert event["event_id"].startswith("event_")
    assert event["created_at"]


def test_an_actor_known_only_by_its_subject_is_still_refused(
    stores: dict[str, list[Any]],
) -> None:
    actor = {key: value for key, value in MANAGER.items() if key != "user_id"}
    actor["sub"] = "admin-1"
    with pytest.raises(HTTPException) as refused:
        _grant(actor, "admin-1")
    assert refused.value.detail == {"code": "capability_self_grant_forbidden"}
    assert stores["grants"] == []


def test_a_target_padded_with_whitespace_is_the_same_identity(
    stores: dict[str, list[Any]],
) -> None:
    with pytest.raises(HTTPException) as refused:
        _grant(MANAGER, " admin-1 ")
    assert refused.value.detail == {"code": "capability_self_grant_forbidden"}
    assert stores["grants"] == []


def test_granting_another_administrator_is_unchanged(stores: dict[str, list[Any]]) -> None:
    response = _grant(MANAGER, "admin-2")
    [grant] = stores["grants"]
    assert grant["user_id"] == "admin-2"
    assert grant["grantor_id"] == "admin-1"
    assert response["targetId"] == "admin-2"
    [(stream_id, event)] = stores["audits"]
    assert stream_id == "admin-2"
    assert event["event_type"] == "capability_granted"


def test_a_caller_without_the_manager_capability_is_refused_first(
    stores: dict[str, list[Any]],
) -> None:
    # Not a manager: the ordinary 403, and no self-grant record for a command
    # this caller could never have issued at all.
    actor = {**MANAGER, "capabilities": {}}
    with pytest.raises(HTTPException) as refused:
        _grant(actor, "admin-1")
    assert refused.value.status_code == 403
    assert stores["audits"] == []
    assert stores["grants"] == []
