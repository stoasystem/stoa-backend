"""What is left of the reviewed AI teacher tools: delivering a stored exercise draft.

Teachers no longer make, review or list drafts: those routes went with #518,
once the teacher help-request page stopped calling them. Drafts already
stored stay readable where an assignment is set from one (`sourceType:
ai_draft`, by a teacher or an automation batch), and an accepted draft set
for its student is still recorded as delivered here.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

from stoa.db.repositories import ai_teacher_tools_repo


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def mark_delivered(assignment: Mapping[str, Any]) -> None:
    """Record on its draft that an accepted exercise draft reached the student.

    Called once its assignment is stored, by whichever path stored it: the
    single assignment a teacher sets (`POST /adaptive/assignments`) or an
    automation batch. Only an assignment the student is shown counts; one
    stored as `draft` does not. Writing it again changes nothing (#519).
    """
    if assignment.get("source_type") != "ai_draft":
        return
    if assignment.get("status") not in {"assigned", "recommended"}:
        return
    draft_id = str(assignment.get("source_id") or "")
    draft = ai_teacher_tools_repo.get_draft(draft_id) if draft_id else None
    if not draft or draft.get("student_delivery_status") == "delivered":
        return
    ai_teacher_tools_repo.update_draft(
        draft_id,
        {
            "student_delivery_status": "delivered",
            "delivered_assignment_id": assignment.get("assignment_id"),
            "delivered_at": assignment.get("created_at") or now_iso(),
        },
        existing=draft,
    )
