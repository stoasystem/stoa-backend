"""Whether a student may ask by voice: the parent's consent switch (#476, part of #469).

One switch per child, off until a parent turns it on. Any parent currently in a
relationship with the child may change it; the last change wins. Every change
is recorded - who, when, the new value - and that record is the consent.

The switch counts as on only while the child has at least one current parent:
a student with no linked parent is off, whatever was stored before.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from stoa.db.repositories import voice_question_consent_repo
from stoa.services import current_relationship
from stoa.services.current_relationship import Verdict


@dataclass(frozen=True, slots=True)
class VoiceQuestionSwitch:
    """The switch as a parent sees it. `changed_by`/`changed_at` are unset until the first change."""

    allowed: bool
    changed_by: str | None = None
    changed_at: str | None = None


class RelationshipNotCurrent(RuntimeError):
    """The parent asked on a relationship that no longer holds."""


def _switch(row: dict[str, Any] | None) -> VoiceQuestionSwitch:
    if row is None:
        return VoiceQuestionSwitch(allowed=False)
    return VoiceQuestionSwitch(
        allowed=row.get("allowed") is True,
        changed_by=str(row.get("changed_by") or "") or None,
        changed_at=str(row.get("changed_at") or "") or None,
    )


def for_parent(student_id: str, *, table: Any | None = None) -> VoiceQuestionSwitch:
    """The switch for a parent already authorized on this child: as stored, off if never set."""
    return _switch(voice_question_consent_repo.get_state(student_id, table=table))


def set_by_parent(
    relationship: Verdict,
    allowed: bool,
    *,
    now: str | None = None,
    table: Any | None = None,
) -> VoiceQuestionSwitch:
    """Record one parent's change, conditioned on the relationship they were authorized on."""
    if not relationship.is_current or not relationship.version:
        raise RelationshipNotCurrent("relationship is not current")
    try:
        row = voice_question_consent_repo.record_change(
            student_id=relationship.student_id,
            parent_id=relationship.parent_id,
            allowed=allowed,
            changed_at=now or datetime.now(UTC).isoformat(),
            change_id=uuid4().hex,
            relationship_version=relationship.version,
            table=table,
        )
    except voice_question_consent_repo.VoiceConsentConflict as exc:
        raise RelationshipNotCurrent(str(exc)) from exc
    return _switch(row)


def allowed_for_student(student_id: str, *, table: Any | None = None) -> bool:
    """What the student's own side sees: on only if a parent turned it on and one is linked now."""
    row = voice_question_consent_repo.get_state(student_id, table=table)
    if row is None or row.get("allowed") is not True:
        return False
    return bool(current_relationship.parents_of(student_id, table=table))
