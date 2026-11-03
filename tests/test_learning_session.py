"""The learning session module's own tests (#227, #228).

`append` makes every message row of a session and returns the put for the
caller's transaction; `open` starts a session behind the student's fence;
`read`, `owned_by` and `history` read the record and the messages back;
`anchored_history` is the exact snapshot a committed question names, and
`committed_message` the checked row its replay reads.
"""

from __future__ import annotations

from typing import Any

import pytest
from fakes.dynamodb import FakeTable
from fakes.learning_session import patch_session_table, seed_conversation, seed_message

from stoa.db.repositories.attachment_repo import AttachmentRepositoryConflict
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.services import learning_session

CONVERSATION = "conv-1"
STUDENT = "student-1"
CREATED_AT = "2026-11-03T10:00:00+00:00"
NEW_ROW = "attribute_not_exists(PK) AND attribute_not_exists(SK)"
STAMPED = {
    "PK",
    "SK",
    "entity_type",
    "schema_version",
    "message_id",
    "conversation_id",
    "student_id",
    "owner_id",
    "account_fence_generation",
    "role",
    "content",
    "created_at",
}

REQUIRED = {
    "student": {"attachment_ids": []},
    "assistant": {"structured": None},
    "teacher": {
        "teacher_response_rich": {"version": 1, "blocks": []},
        "teacher_response_format": "stoa_teacher_reply_v1",
    },
    "system": {"system_event": "teacher_help_requested"},
}


def _append(role: str, *, message_id: str = "msg-1", generation: int = 3, **fields):
    return learning_session.append(
        CONVERSATION,
        role=role,
        message_id=message_id,
        student_id=STUDENT,
        generation=generation,
        content="Wie kürze ich Brüche?",
        created_at=CREATED_AT,
        **fields,
    )


def _row(operation: dict) -> dict:
    assert set(operation) == {"Put"}
    assert operation["Put"]["ConditionExpression"] == NEW_ROW
    assert set(operation["Put"]) == {"Item", "ConditionExpression"}
    return operation["Put"]["Item"]


# ── append ───────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", sorted(REQUIRED))
def test_every_role_s_row_is_stamped_with_its_key_schema_owner_and_fence(role):
    row = _row(_append(role, **REQUIRED[role]))

    assert {key: row[key] for key in STAMPED} == {
        "PK": "CONV#conv-1",
        "SK": "MSG#msg-1",
        "entity_type": "conversation_message",
        "schema_version": "conversation-message.v1",
        "message_id": "msg-1",
        "conversation_id": CONVERSATION,
        "student_id": STUDENT,
        "owner_id": STUDENT,
        "account_fence_generation": 3,
        "role": role,
        "content": "Wie kürze ich Brüche?",
        "created_at": CREATED_AT,
    }


def test_a_student_message_keeps_its_attachment_ids_and_quote_only_when_given():
    plain = _row(_append("student", attachment_ids=[]))
    assert set(plain) - STAMPED == {"attachment_ids"}
    assert plain["attachment_ids"] == []

    quoted = _row(
        _append(
            "student",
            attachment_ids=("att-1", "att-2"),
            quote={"text": "1/2", "source": "assistant"},
        )
    )
    assert set(quoted) - STAMPED == {"attachment_ids", "quote"}
    assert quoted["attachment_ids"] == ["att-1", "att-2"]
    assert quoted["quote"] == {"text": "1/2", "source": "assistant"}

    assert "quote" not in _row(_append("student", attachment_ids=[], quote=None))


def test_an_assistant_message_keeps_structured_a_set_target_and_its_allowance():
    bare = _row(_append("assistant", structured=None, target_unit_id=None))
    assert set(bare) - STAMPED == {"structured"}
    assert bare["structured"] is None
    assert "target_unit_id" not in _row(_append("assistant", structured=None, target_unit_id=""))

    full = _row(
        _append(
            "assistant",
            structured={"sections": []},
            target_unit_id="unit-7",
            allowance={"allowance_effect_id": "a" * 64, "provider_input_tokens": 12},
        )
    )
    assert set(full) - STAMPED == {
        "structured",
        "target_unit_id",
        "allowance_effect_id",
        "provider_input_tokens",
    }
    assert full["structured"] == {"sections": []}
    assert full["target_unit_id"] == "unit-7"
    assert full["provider_input_tokens"] == 12


@pytest.mark.parametrize("key", ["owner_id", "account_fence_generation", "structured"])
def test_an_allowance_cannot_overwrite_a_field_of_the_row(key):
    with pytest.raises(ValueError):
        _append("assistant", structured=None, allowance={key: "other"})


def test_a_teacher_reply_keeps_a_named_author_stripped_and_attachments_only_when_given():
    bare = _row(_append("teacher", **REQUIRED["teacher"]))
    assert set(bare) - STAMPED == {"teacher_response_rich", "teacher_response_format"}

    for blank in (None, "", "   ", 42):
        assert "author_name" not in _row(
            _append("teacher", author_name=blank, **REQUIRED["teacher"])
        )

    full = _row(
        _append(
            "teacher",
            author_name="  Frau Muster ",
            attachment_ids=["att-1"],
            **REQUIRED["teacher"],
        )
    )
    assert full["author_name"] == "Frau Muster"
    assert full["attachment_ids"] == ["att-1"]
    assert full["teacher_response_rich"] == {"version": 1, "blocks": []}
    assert full["teacher_response_format"] == "stoa_teacher_reply_v1"


def test_a_system_message_always_carries_its_escalation_message():
    silent = _row(_append("system", message_id=CONVERSATION, **REQUIRED["system"]))
    assert silent["SK"] == "MSG#conv-1"
    assert set(silent) - STAMPED == {"system_event", "escalation_message"}
    assert silent["escalation_message"] is None

    noted = _row(
        _append(
            "system",
            message_id=CONVERSATION,
            escalation_message="Bitte hilf mir",
            **REQUIRED["system"],
        )
    )
    assert noted["system_event"] == "teacher_help_requested"
    assert noted["escalation_message"] == "Bitte hilf mir"


def test_an_unknown_role_is_refused():
    with pytest.raises(ValueError):
        _append("parent")


@pytest.mark.parametrize(
    ("role", "field"),
    [
        ("student", "structured"),
        ("assistant", "attachment_ids"),
        ("teacher", "quote"),
        ("system", "author_name"),
        ("student", "system_event"),
    ],
)
def test_a_field_of_another_role_is_refused(role, field):
    with pytest.raises(ValueError):
        _append(role, **REQUIRED[role], **{field: "x"})


@pytest.mark.parametrize("role", sorted(REQUIRED))
def test_a_role_s_required_field_cannot_be_left_out(role):
    for field in REQUIRED[role]:
        fields = {key: value for key, value in REQUIRED[role].items() if key != field}
        with pytest.raises(ValueError):
            _append(role, **fields)


@pytest.mark.parametrize("generation", [0, -1, True, 1.0, "1"])
def test_a_generation_that_is_not_a_positive_int_is_refused(generation):
    with pytest.raises(AttachmentRepositoryConflict):
        _append("student", attachment_ids=[], generation=generation)


def test_a_message_without_a_student_is_refused():
    with pytest.raises(AttachmentRepositoryConflict):
        learning_session.append(
            CONVERSATION,
            role="student",
            message_id="msg-1",
            student_id="",
            generation=1,
            content="hi",
            created_at=CREATED_AT,
            attachment_ids=[],
        )


def test_a_row_that_would_not_read_back_is_never_produced():
    with pytest.raises(AttachmentDecisionError):
        _append("student", attachment_ids=[], message_id="")
    with pytest.raises(AttachmentDecisionError):
        learning_session.append(
            CONVERSATION,
            role="student",
            message_id="msg-1",
            student_id=STUDENT,
            generation=1,
            content="hi",
            created_at="",
            attachment_ids=[],
        )


# ── committed_message ────────────────────────────────────────────────────────


@pytest.fixture
def table(monkeypatch):
    fake = FakeTable()
    patch_session_table(monkeypatch, fake)
    return fake


def test_a_committed_message_is_read_back_as_it_was_appended(table):
    table.seed(_row(_append("student", attachment_ids=["att-1"])))

    row = learning_session.committed_message(CONVERSATION, "msg-1", student_id=STUDENT)

    assert row["message_id"] == "msg-1"
    assert row["attachment_ids"] == ["att-1"]
    assert row["role"] == "student"


def test_a_message_that_is_not_there_is_unavailable(table):
    with pytest.raises(AttachmentDecisionError) as raised:
        learning_session.committed_message(CONVERSATION, "msg-1", student_id=STUDENT)
    assert raised.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": "conversation-message.v0"},
        {"entity_type": "conversation_teacher_note"},
        {"student_id": "student-2"},
        {"conversation_id": "conv-2"},
        {"message_id": "msg-2"},
        {"role": "parent"},
        {"content": None},
    ],
)
def test_a_malformed_or_foreign_row_is_unavailable(table, change):
    table.seed({**_row(_append("student", attachment_ids=[])), **change})

    with pytest.raises(AttachmentDecisionError) as raised:
        learning_session.committed_message(CONVERSATION, "msg-1", student_id=STUDENT)
    assert raised.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE


# ── open ─────────────────────────────────────────────────────────────────────


def _open() -> dict[str, object]:
    return learning_session.open(
        STUDENT, subject="Mathematik", grade="Grade 6", title="Brüche", now=CREATED_AT
    )


def test_open_stores_the_record_seed_conversation_plants(table):
    table.seed_active_account(STUDENT, generation=3)

    record = _open()

    conversation_id = record["conversation_id"]
    stored = table.rows[(f"CONV#{conversation_id}", "CONV")]
    planted = FakeTable()
    seed_conversation(
        planted,
        conversation_id=conversation_id,
        student_id=STUDENT,
        subject="Mathematik",
        grade="Grade 6",
        title="Brüche",
        now=CREATED_AT,
        generation=3,
    )
    assert stored == planted.rows[(f"CONV#{conversation_id}", "CONV")]
    assert stored["account_fence_generation"] == 3
    assert record["owner_id"] == STUDENT


def test_open_refuses_a_student_whose_account_is_being_deleted(table):
    table.seed(
        {
            "PK": f"USER#{STUDENT}",
            "SK": "ACCOUNT_FENCE",
            "status": "deletion_pending",
            "generation": 3,
        }
    )

    with pytest.raises(AttachmentDecisionError) as raised:
        _open()

    assert raised.value.code is AttachmentErrorCode.UPLOAD_NOT_FOUND
    assert not [key for key in table.rows if key[0].startswith("CONV#")]


def test_open_refuses_a_student_without_a_fence(table):
    with pytest.raises(AttachmentDecisionError) as raised:
        _open()

    assert raised.value.code is AttachmentErrorCode.UPLOAD_NOT_FOUND


# ── read and owned_by ────────────────────────────────────────────────────────


def test_read_is_the_record_or_none(table):
    seed_conversation(table, conversation_id=CONVERSATION, student_id=STUDENT)

    assert learning_session.read(CONVERSATION) == table.rows[(f"CONV#{CONVERSATION}", "CONV")]
    assert learning_session.read("conv-missing") is None


def test_owned_by_is_true_only_for_the_owner(table):
    seed_conversation(table, conversation_id=CONVERSATION, student_id=STUDENT)

    assert learning_session.owned_by(CONVERSATION, STUDENT) is True
    assert learning_session.owned_by(CONVERSATION, "student-2") is False
    assert learning_session.owned_by("conv-missing", STUDENT) is False


# ── history ──────────────────────────────────────────────────────────────────


def _message(table, message_id: str, role: str, created_at: str, content: str = "") -> dict:
    return seed_message(
        table,
        conversation_id=CONVERSATION,
        role=role,
        message_id=message_id,
        student_id=STUDENT,
        content=content or message_id,
        created_at=created_at,
    )


def _strong_queries(table) -> list[dict[str, Any]]:
    return [
        request
        for operation, request in table.requests
        if operation == "query" and request.get("ConsistentRead") is True
    ]


def test_history_is_every_message_oldest_first_across_pages(table):
    # The ids run against the order of sending, as random ids may.
    _message(table, "c", "student", "2026-11-03T10:00:00+00:00")
    _message(table, "b", "assistant", "2026-11-03T10:00:05+00:00")
    _message(table, "a", "system", "2026-11-03T10:01:00+00:00")
    table.page_item_cap = 1

    history = learning_session.history(CONVERSATION)

    assert all(isinstance(message, learning_session.Message) for message in history)
    assert [(message.id, message.role) for message in history] == [
        ("c", "student"),
        ("b", "assistant"),
        ("a", "system"),
    ]
    assert history[0].content == "c"
    assert history[0].student_id == STUDENT
    queries = _strong_queries(table)
    assert len(queries) >= 3
    assert any("ExclusiveStartKey" in request for request in queries)


def test_history_of_a_session_without_messages_is_empty(table):
    assert learning_session.history(CONVERSATION) == []


def test_history_refuses_a_malformed_row(table):
    _message(table, "a", "student", "2026-11-03T10:00:00+00:00")
    table.rows[(f"CONV#{CONVERSATION}", "MSG#a")]["schema_version"] = "conversation-message.v0"

    with pytest.raises(AttachmentDecisionError) as raised:
        learning_session.history(CONVERSATION)
    assert raised.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE


# ── anchored_history (moved from test_phase473_conversation_replay.py) ───────


def _two_messages_and_their_fingerprint(table) -> str:
    """A session with one exchange in it, and the fingerprint a question took of it."""
    _message(table, "student-old", "student", "2026-07-17T00:00:00Z", "original question")
    _message(table, "assistant-old", "assistant", "2026-07-17T00:00:01Z", "original reply")
    return learning_session.history_fingerprint(learning_session.history_rows(CONVERSATION))


def _anchored(fingerprint: str) -> list[dict]:
    return learning_session.anchored_history(
        CONVERSATION,
        owner_id=STUDENT,
        message_ids=["student-old", "assistant-old"],
        fingerprint=fingerprint,
    )


def test_history_snapshot_is_consistent_paginated_ordered_and_ignores_later_rows(table) -> None:
    fingerprint = _two_messages_and_their_fingerprint(table)
    _message(table, "student-later", "student", "2099-07-17T00:00:09Z", "later private canary")
    table.page_item_cap = 1
    table.requests.clear()

    snapshot = _anchored(fingerprint)

    # Read page by page, each page strongly consistent.
    history = _strong_queries(table)
    assert len(history) >= 3
    assert any("ExclusiveStartKey" in request for request in history)
    assert [row["content"] for row in snapshot] == ["original question", "original reply"]
    assert "later private canary" not in repr(snapshot)


@pytest.mark.parametrize("mode", ["missing", "duplicate", "changed", "malformed-page"])
def test_history_snapshot_rejects_missing_duplicate_changed_and_malformed_rows(
    table, monkeypatch, mode: str
) -> None:
    fingerprint = _two_messages_and_their_fingerprint(table)
    if mode == "missing":
        del table.rows[(f"CONV#{CONVERSATION}", "MSG#assistant-old")]
    elif mode == "duplicate":
        table.seed(
            {
                **table.rows[(f"CONV#{CONVERSATION}", "MSG#student-old")],
                "SK": "MSG#student-old-again",
            }
        )
    elif mode == "changed":
        table.rows[(f"CONV#{CONVERSATION}", "MSG#assistant-old")]["content"] = "changed after command"
    else:
        query = table.query

        def malformed(**kwargs: Any) -> Any:
            page = query(**kwargs)
            return {**page, "Items": {}}

        monkeypatch.setattr(table, "query", malformed)

    with pytest.raises(AttachmentDecisionError) as captured:
        _anchored(fingerprint)

    assert captured.value.code is AttachmentErrorCode.UPLOAD_SERVICE_UNAVAILABLE
