"""Knowledge points the knowledge base lacks, as Ask answers name them (#142).

When an answer names a knowledge point that matches no star on the student's
map, the model wrote it freely. Each such name is counted per subject, for the
admin's knowledge-base gap list (the page is a later ticket; the data is kept
from now on).

A record is a count, not a log: it holds the subject, the name as it was first
written, the count and when it was first and last seen. It names no student,
conversation or question, so it is not the student's data and outlives every
account that contributed to it. The name is still free text a student can
steer the model into writing, so two things keep it from holding what it
should not:

* a name that looks like personal data - an e-mail address, a phone number, a
  long run of digits - is not recorded or counted at all;
* a record expires `RETENTION_DAYS` after the name was last seen, through the
  table's TTL attribute, so a name nobody repeats goes away on its own.

The counts are written inside the transaction that stores the answer
(`attachment_repo.complete_message_command`), whose assistant-message put only
succeeds once: an answer replayed, retried or finished by another attempt
counts once, and only an answer that was stored counts at all.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime, timedelta

ENTITY_TYPE = "knowledge_gap"
#: Longer than any knowledge point's name; a longer one is cut, not refused.
MAX_NAME_CHARS = 120
#: Most names one answer counts. A transaction holds 100 items in all.
MAX_PER_ANSWER = 10
#: How long a record outlives the last time its name was seen.
RETENTION_DAYS = 180

_PERSONAL_DATA = (
    # An e-mail address.
    re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+"),
    # A phone number: nine digits or more, however they are grouped.
    re.compile(r"\+?\d(?:[\s\-/.()]*\d){8,}"),
    # A long run of digits: an account, card or AHV number, a code.
    re.compile(r"\d{7,}"),
)


def _written(name: str) -> str:
    return " ".join(name.split())[:MAX_NAME_CHARS]


def looks_personal(name: str) -> bool:
    """Whether a name looks like personal data rather than a knowledge point."""
    return any(pattern.search(name) for pattern in _PERSONAL_DATA)


def gap_key(subject: str, name: str) -> dict[str, str]:
    """One record per subject and name, whatever its case or spacing."""
    return {
        "PK": f"KNOWLEDGE_GAP#{subject}",
        "SK": f"NAME#{_written(name).casefold()}",
    }


def _expires_at(seen_at: str) -> int:
    """The TTL in epoch seconds, as the table's `expires_at` attribute holds it."""
    return int((datetime.fromisoformat(seen_at) + timedelta(days=RETENTION_DAYS)).timestamp())


def count_updates(subject: str, names: Sequence[str], *, seen_at: str) -> list[dict[str, object]]:
    """The transaction updates that count each name once for this answer.

    `seen_at` is when the answer was stored, as an ISO timestamp with its
    offset; the record expires `RETENTION_DAYS` after it.
    """
    updates: dict[str, dict[str, object]] = {}
    for name in names:
        written = _written(name)
        if not written or looks_personal(name):
            continue
        key = gap_key(subject, written)
        if key["SK"] in updates:
            continue
        updates[key["SK"]] = {
            "Update": {
                "Key": key,
                "UpdateExpression": (
                    "SET entity_type=:entity, subject=:subject, "
                    "#name=if_not_exists(#name, :name), "
                    "first_seen_at=if_not_exists(first_seen_at, :seen_at), "
                    "last_seen_at=:seen_at, expires_at=:expires_at "
                    "ADD #count :one"
                ),
                "ExpressionAttributeNames": {"#name": "name", "#count": "count"},
                "ExpressionAttributeValues": {
                    ":entity": ENTITY_TYPE,
                    ":subject": subject,
                    ":name": written,
                    ":seen_at": seen_at,
                    ":expires_at": _expires_at(seen_at),
                    ":one": 1,
                },
            }
        }
        if len(updates) == MAX_PER_ANSWER:
            break
    return list(updates.values())
