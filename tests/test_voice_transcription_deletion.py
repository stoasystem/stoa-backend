"""#477: what account deletion does to a student's voice transcription counter.

The day's counter (`STUDENT#<student>/VOICE_TRANSCRIPTIONS_DAY#<day>`) is the
student's own. Deleting the student removes it through the deletion branches,
driven as `test_voice_question_consent_deletion` drives them; its TTL is no
substitute, since TTL can lag by days.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

import test_chat_help_request_lifecycle as lifecycle
import test_voice_question_consent_deletion as consent_deletion
from stoa.db.repositories import voice_transcription_usage_repo as usage_repo

STUDENT = lifecycle.STUDENT
DAY = "2026-11-17"


def _counter_rows(table) -> dict[tuple[str, str], dict]:
    return {
        key: row
        for key, row in table.rows.items()
        if key[1].startswith(usage_repo.SK_PREFIX)
        or row.get("entity_type") == usage_repo.ENTITY_TYPE
    }


@pytest.fixture
def table(monkeypatch):
    table = lifecycle.build_table(monkeypatch)
    lifecycle.keep_waiting(monkeypatch)
    expires = int(datetime(2026, 11, 19, tzinfo=UTC).timestamp())
    usage_repo.admit(STUDENT, DAY, limit=30, expires_at=expires)
    usage_repo.admit(STUDENT, "2026-11-16", limit=30, expires_at=expires)
    assert usage_repo.count(STUDENT, DAY) == 1
    assert len(_counter_rows(table)) == 2
    return table


def test_deleting_the_student_removes_every_transcription_counter(table) -> None:
    sealed, history = consent_deletion._delete(table, STUDENT)

    assert sealed, history
    assert _counter_rows(table) == {}
