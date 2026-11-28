"""A student's account deletion runs to a valid seal: stoasystem/stoa-backend#78.

Every deletion branch was tested on its own mocked or synthetic data, and no
test ran them together, so four independent faults each kept a real deletion
from ever sealing: the conversation and practice branches re-found their own
tombstones, the identity branch refused to replay its own revoke debt, and
the attachments branch declared itself complete one clean pass early and was
then never run again. No deletion command exists in production yet.

This drives the whole deletion as production runs it (the catalog's flow
since #641; the branches went with #642), over the shared table double with
production-shaped rows, stubbing only external clients (Cognito, S3), until
the command completes.
"""

from __future__ import annotations

import json

import pytest

import deletion_helpers
import test_chat_help_request_lifecycle as lifecycle
from fakes.learning_session import seed_message
from stoa import aws
from stoa.aws import Kind

NOW = "2026-09-28T23:59:00+00:00"
# The teacher's reply, the student's message, a question-lane question, and the
# message the student asked a teacher with, which since #189 is on the help
# request's own record rather than the conversation row.
PRIVATE = (
    "Probier jetzt 15 : 5.",
    "private student message",
    "private question",
    "Step 2 makes no sense to me.",
    # The invitation the account was opened with: it names the account by
    # `account_id` only, and outlived the account on both deletion paths.
    "invited.person@example.invalid",
    "Invited Private Person",
)


class _ExternalClient:
    """Any external client call answers an empty success."""

    class exceptions:
        class UserNotFoundException(Exception):
            pass

    def __getattr__(self, _name):
        return lambda *_args, **_kwargs: {}


@pytest.fixture
def table(monkeypatch):
    table = lifecycle.table.__wrapped__(monkeypatch)
    lifecycle._dispatch_to(table, lifecycle.TEACHER)
    lifecycle._accept_and_reply(lifecycle._client(), PRIVATE[0])
    student = lifecycle.STUDENT
    seed_message(
        table,
        conversation_id=lifecycle.CONV,
        role="student",
        message_id="student-1",
        student_id=student,
        content=PRIVATE[1],
        created_at="2026-09-28T12:01:00+00:00",
    )
    table.seed(
        {
            "PK": "QUESTION#q-lane", "SK": "META", "entity_type": "question", "schema_version": "question.v1",
            "question_id": "q-lane", "student_id": student, "owner_id": student, "status": "resolved",
            "version": 3, "account_fence_generation": 1, "subject": "math", "content": PRIVATE[2],
            "created_at": "2026-09-27T10:00:00+00:00",
        },
        # Practice progress and the usage ledger: every student who asked a
        # question or practised has rows like these.
        {"PK": f"PROGRESS#{student}", "SK": "LESSON#l1", "student_id": student, "completed": True},
        {"PK": f"USAGE_LEDGER#{student}", "SK": "EVENT#e1", "student_id": student, "action": "question"},
        {
            "PK": "ACCOUNT_INVITATION#digest-1", "SK": "META", "entity_type": "account_invitation",
            "invitation_id": "inv-1", "token_digest": "digest-1", "account_id": student,
            "role": "student", "email": PRIVATE[4], "full_name": PRIVATE[5], "status": "used",
            "version": 2, "invited_by": "admin-1", "issued_at": "2026-09-20T10:00:00+00:00",
        },
        # Someone else's invitation, issued by the same administrator: it stays.
        {
            "PK": "ACCOUNT_INVITATION#digest-2", "SK": "META", "entity_type": "account_invitation",
            "invitation_id": "inv-2", "token_digest": "digest-2", "account_id": "student-other",
            "role": "student", "email": "other@example.invalid", "full_name": "Other Person",
            "status": "issued", "version": 1, "invited_by": "admin-1",
        },
    )
    # Rows seeded here, as their writers would have filed them under the student.
    deletion_helpers.register(
        table, *(row for (pk, _), row in table.rows.items() if not pk.startswith("USER#"))
    )
    return table


def test_a_student_with_a_conversation_and_practice_can_be_deleted(table, monkeypatch):
    aws.install({Kind.S3: _ExternalClient(), Kind.COGNITO: _ExternalClient()})
    command = deletion_helpers.delete_account(lifecycle.STUDENT)

    assert command["status"] == "complete"
    left = [key for key, row in table.rows.items() if any(text in json.dumps(row, default=str) for text in PRIVATE)]
    assert left == [], left
    assert ("ACCOUNT_INVITATION#digest-1", "META") not in table.rows
    # A revoke debt, where one was opened, is closed one way or the other.
    debts = [row for (_, sk), row in table.rows.items() if sk.startswith("PROVIDER_REVOKE#")]
    assert all(row["status"] != "pending" for row in debts), debts
    assert table.rows[("ACCOUNT_INVITATION#digest-2", "META")]["full_name"] == "Other Person"


def test_an_account_with_no_provider_identity_does_not_leave_its_revoke_debt_pending(table):
    """Invited and never signed in: nothing answers to the revoke debt.

    The first deletion on the registry path left `PROVIDER_REVOKE#…` saying
    `pending` for good. It is closed as `nothing_to_revoke` once the deletion
    has found nothing to revoke, and a debt a revoke did close is not rewritten.
    """
    from stoa.db.repositories import account_deletion_repo

    aws.install({Kind.S3: _ExternalClient(), Kind.COGNITO: _ExternalClient()})
    student = lifecycle.STUDENT
    for key in [key for key, row in table.rows.items()
                if row.get("entity_type") in {"identity_binding", "user_identity_inventory"}]:
        del table.rows[key]
    debt = (f"USER#{student}", f"PROVIDER_REVOKE#{1:020d}")

    command = deletion_helpers.delete_account(student)

    assert command["status"] == "complete"
    # Nothing to revoke: no debt is left saying `pending`.
    assert table.rows.get(debt, {}).get("status") in {
        None, account_deletion_repo.PROVIDER_REVOKE_UNUSED
    }

    table.seed({"PK": debt[0], "SK": debt[1], "status": "complete"})
    assert not account_deletion_repo.close_unused_provider_revoke_debt(
        user_id=student, generation=1, closed_at=NOW
    )
    assert table.rows[debt]["status"] == "complete"
