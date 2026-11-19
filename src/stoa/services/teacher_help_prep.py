"""What a teacher's prep table shows of a help request's conversation (#517).

The table is built from what was said, with no model in between: the
student's first question, their last question before asking for a teacher,
everything they uploaded, and the stars their Ask answers touched. The rules
for which message is which live here and nowhere else; the client does not
pick them out of the messages itself.

These are pure functions over what the detail route already read: the
conversation's messages (`learning_session.history`, oldest first) and its
asked-knowledge records (`asked_knowledge_repo.list_for_conversation`, newest
first).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from stoa.services import learning_session


@dataclass(frozen=True)
class Questions:
    """The student's first question, and their last one before asking for a teacher.

    `last` is `None` when it is the first one: the table shows one row then.
    """

    first: learning_session.Message | None
    last: learning_session.Message | None


def questions(
    messages: Sequence[learning_session.Message], *, asked_at: str | None
) -> Questions:
    """The first and the last question of `messages`, oldest first.

    A question is a student message that says something or carries a file.
    The last one is the latest sent no later than `asked_at`, when the student
    asked for a teacher; what they sent after does not count. Without a
    readable `asked_at`, every question counts.
    """
    asked = [message for message in messages if _is_question(message)]
    if not asked:
        return Questions(first=None, last=None)
    cutoff = _moment(asked_at)
    before = [
        message
        for message in asked
        if cutoff is None or (_moment(message.created_at) or cutoff) <= cutoff
    ]
    first = asked[0]
    last = before[-1] if before else None
    return Questions(first=first, last=None if last is None or last.id == first.id else last)


def uploads(messages: Iterable[learning_session.Message]) -> list[str]:
    """The ids of every file the student sent in the conversation, in the order sent, once each."""
    seen: dict[str, None] = {}
    for message in messages:
        if message.role != "student":
            continue
        for attachment_id in message.attachment_ids:
            if attachment_id:
                seen.setdefault(attachment_id, None)
    return list(seen)


def asked_star_ids(records: Iterable[Mapping[str, Any]]) -> list[str]:
    """The stars the conversation's Ask answers named, newest first, once each.

    Only the points that were stars on the student's map carry a unit id; the
    names the model wrote freely do not, and are not stars.
    """
    seen: dict[str, None] = {}
    for record in records:
        for unit_id in record.get("unit_ids") or []:
            if isinstance(unit_id, str) and unit_id:
                seen.setdefault(unit_id, None)
    return list(seen)


def _is_question(message: learning_session.Message) -> bool:
    return message.role == "student" and (
        bool(message.content.strip()) or bool(message.attachment_ids)
    )


def _moment(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
