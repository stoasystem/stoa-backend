"""The learning session module: appending a message and reading one back (#227).

`append` makes every message row of a session and returns the put for the
caller's transaction; `committed_message` is the checked read the question's
replay uses. Step 3 of #205 (#228) adds the module's other tests here.
"""

from __future__ import annotations

import pytest
from fakes.dynamodb import FakeTable

from stoa.db.repositories.attachment_repo import AttachmentRepositoryConflict
from stoa.security.attachment_errors import AttachmentDecisionError, AttachmentErrorCode
from stoa.services import learning_session
from stoa.services.learning_session import _store as learning_session_store

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
    monkeypatch.setattr(learning_session_store, "get_table", lambda: fake)
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
