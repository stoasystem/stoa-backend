"""#476: what account deletion does to a child's voice questions consent rows.

The switch and its change records live in the student's own partition
(`STUDENT#<student>`). Each test drives every deletion branch the way
`continue_command` does, over the shared table double, until
`validate_deletion_seal` accepts the command, as `test_student_deletion_seals`
does; only external clients (Cognito, S3) are stubbed.

- Deleting the student removes the switch and every change record.
- Deleting a parent leaves the child's switch and record as they were,
  `changed_by` still naming that parent. This pins today's behaviour so the
  decision on it is made against a tested fact; it is not a requirement.
"""

from __future__ import annotations

import pytest

import test_chat_help_request_lifecycle as lifecycle
from stoa import aws
from stoa.aws import Kind
from stoa.db.repositories import voice_question_consent_repo
from stoa.services import (
    account_deletion_service as service,
    current_relationship,
    parent_link_service,
    voice_questions,
)

COMMAND_ID = "cmd-voice"
NOW = "2026-11-17T23:59:00+00:00"
STUDENT = lifecycle.STUDENT
PARENT = "parent-66"
OTHER_PARENT = "parent-67"
CHANGES = (
    (PARENT, True, "2026-11-16T10:00:00+00:00"),
    (OTHER_PARENT, False, "2026-11-16T11:00:00+00:00"),
    (PARENT, True, "2026-11-16T12:00:00+00:00"),
)


class _ExternalClient:
    """Any external client call answers an empty success."""

    class exceptions:
        class UserNotFoundException(Exception):
            pass

    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: {}


def _parent_rows(parent_id: str) -> list[dict]:
    return [
        {
            "PK": f"USER#{parent_id}",
            "SK": "PROFILE",
            "user_id": parent_id,
            "role": "parent",
            "account_status": "active",
            "version": 1,
        },
        {"PK": f"USER#{parent_id}", "SK": "ACCOUNT_FENCE", "status": "active", "generation": 1},
    ]


def _consent_rows(table) -> dict[tuple[str, str], dict]:
    return {
        key: row
        for key, row in table.rows.items()
        if key[0] == f"STUDENT#{STUDENT}"
        and (
            key[1] == voice_question_consent_repo.STATE_SK
            or key[1].startswith(voice_question_consent_repo.CHANGE_SK_PREFIX)
        )
    }


@pytest.fixture
def table(monkeypatch):
    table = lifecycle.build_table(monkeypatch)
    lifecycle.keep_waiting(monkeypatch)
    table.seed(*_parent_rows(PARENT), *_parent_rows(OTHER_PARENT))
    for parent_id in (PARENT, OTHER_PARENT):
        parent_link_service.assign_link(
            parent_id=parent_id, student_id=STUDENT, actor_id="admin-1", now=CHANGES[0][2]
        )
    for parent_id, allowed, at in CHANGES:
        relationship = current_relationship.judge(parent_id, STUDENT)
        assert relationship.is_current, relationship
        voice_questions.set_by_parent(relationship, allowed, now=at)
    rows = _consent_rows(table)
    assert len(rows) == 1 + len(CHANGES), sorted(rows)
    return table


def _delete(table, user_id: str) -> tuple[bool, dict]:
    """Run every branch for `user_id` until the seal holds; return the verdict and history."""
    table.rows[(f"USER#{user_id}", "ACCOUNT_FENCE")].update(
        {"status": "deletion_pending", "command_id": COMMAND_ID, "entity_type": "account_fence",
         "user_id": user_id, "version": 2}
    )
    aws.install({Kind.S3: _ExternalClient(), Kind.COGNITO: _ExternalClient()})
    seal = service.load_private_store_seal()
    results: dict = {}
    command = {"user_id": user_id, "generation": 1, "command_id": COMMAND_ID, "branch_results": results}
    history: dict = {branch: [] for branch in service.ACCOUNT_DELETION_BRANCH_IDS}
    for _run in range(8):
        for branch_id in service.ACCOUNT_DELETION_BRANCH_IDS:
            previous = results.get(branch_id) or {}
            if previous.get("status") == "complete" and previous.get("quiescent") is True:
                continue
            try:
                result = service.BRANCH_HANDLERS[branch_id](command=command, previous=previous)
            except Exception as exc:  # as continue_command records it
                history[branch_id].append(f"raised {type(exc).__name__}")
                result = service.BranchResult("retryable", debt_counts={"dependency": 1})
            contract = seal["branch_contracts"][branch_id]
            results[branch_id] = result.persisted(
                NOW, generation=1, handler_version=contract["handler_version"],
                subfamilies=contract["subfamilies"],
            )
            history[branch_id].append(f"{result.status}/{result.epoch}")
    full_command = {
        "status": "running", "command_id": COMMAND_ID, "generation": 1,
        "inventory_sha256": seal["inventory_sha256"],
        "branch_ids": list(service.ACCOUNT_DELETION_BRANCH_IDS),
        "branch_contracts": seal["branch_contracts"], "branch_results": results,
    }
    fence = dict(table.rows[(f"USER#{user_id}", "ACCOUNT_FENCE")], generation=1)
    return service.validate_deletion_seal(command=full_command, fence=fence, seal=seal), history


def test_deleting_the_student_removes_the_switch_and_every_change_record(table) -> None:
    sealed, history = _delete(table, STUDENT)

    assert sealed, history
    assert _consent_rows(table) == {}
    left = [
        key for key, row in table.rows.items()
        if str(row.get("entity_type") or "").startswith(voice_question_consent_repo.ENTITY_TYPE)
    ]
    assert left == [], left


def test_deleting_a_parent_leaves_the_childs_switch_and_record_naming_that_parent(table) -> None:
    before = {key: dict(row) for key, row in _consent_rows(table).items()}

    sealed, history = _delete(table, PARENT)

    assert sealed, history
    after = _consent_rows(table)
    assert after == before
    state = after[(f"STUDENT#{STUDENT}", voice_question_consent_repo.STATE_SK)]
    assert (state["allowed"], state["changed_by"]) == (True, PARENT)
    assert [row["changed_by"] for _, row in sorted(after.items()) if row is not state] == [
        PARENT, OTHER_PARENT, PARENT,
    ]
    # The deleted parent's own link to the child is gone; the other parent's stands.
    assert not current_relationship.judge(PARENT, STUDENT).is_current
    assert current_relationship.judge(OTHER_PARENT, STUDENT).is_current
