"""The usage events the statistics table accepts, and the props each may carry.

Closed on both ends: an event not listed is not stored, and a prop not listed
for its event is stripped. No prop holds an account id, a name or anything a
student wrote; the web client's `userId`, `studentId`, `conversationId` and
`requestId` props are stripped for that reason.

`CLIENT` events arrive at `POST /analytics/events`; `SERVER` events are
recorded by the backend itself and refused from the client, so a browser
cannot forge them.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal, NamedTuple


class Prop(NamedTuple):
    kind: Literal["str", "num", "bool"]
    max_length: int = 64


_STR = Prop("str")
_NUM = Prop("num")
_BOOL = Prop("bool")
_ROUTE = Prop("str", 128)

CLIENT = "client"
SERVER = "server"


class EventSpec(NamedTuple):
    source: str
    props: Mapping[str, Prop]


def _client(**props: Prop) -> EventSpec:
    return EventSpec(CLIENT, props)


def _server(**props: Prop) -> EventSpec:
    return EventSpec(SERVER, props)


EVENTS: Mapping[str, EventSpec] = {
    # The web client's events (`analyticsClient.ts`).
    "user_login": _client(role=_STR),
    "user_register": _client(role=_STR),
    "chat_conversation_created": _client(subject=_STR),
    "chat_message_sent": _client(hasAttachments=_BOOL),
    "chat_response_started": _client(),
    "chat_response_completed": _client(),
    "chat_response_stopped": _client(),
    "file_uploaded": _client(),
    "teacher_help_requested": _client(status=_STR, mode=_STR),
    "teacher_help_request_failed": _client(reason=_STR, mode=_STR),
    "login_submitted": _client(),
    "login_authenticated": _client(role=_STR, msSinceSubmit=_NUM),
    "login_first_screen_ready": _client(route=_ROUTE, msSinceSubmit=_NUM),
    "teacher_help_assigned": _client(),
    "teacher_help_resolved": _client(),
    "parent_child_summary_viewed": _client(),
    "parent_report_viewed": _client(periodLabel=_STR),
    "parent_upgrade_cta_clicked": _client(source=_STR),
    "pricing_page_viewed": _client(),
    "pricing_plan_selected": _client(plan=_STR),
    "checkout_started": _client(plan=_STR, mode=_STR),
    "plan_review_completed": _client(plan=_STR),
    "billing_page_viewed": _client(selectedPlan=_STR),
    "feature_locked_viewed": _client(feature=_STR, reason=_STR),
    "upgrade_prompt_clicked": _client(feature=_STR),
    "parent_landing_viewed": _client(),
    "parent_value_cta_clicked": _client(source=_STR),
    "referral_page_viewed": _client(),
    "referral_link_copied": _client(),
    "teacher_availability_viewed": _client(),
    "teacher_availability_updated": _client(),
    "teacher_credential_uploaded": _client(),
    "support_ticket_created": _client(),
    "support_ticket_viewed": _client(),
    "admin_analytics_viewed": _client(),
    "utm_captured": _client(source=_STR, medium=_STR, campaign=_STR),
    "billing_checkout_started": _client(plan=_STR),
    "billing_virtual_checkout_completed": _client(plan=_STR),
    "billing_virtual_checkout_canceled": _client(plan=_STR),
    "teacher_request_opened": _client(),
    "teacher_request_status_updated": _client(status=_STR),
    "teacher_time_to_first_action_recorded": _client(durationMs=_NUM),
    "teacher_note_added": _client(),
    "feedback_submitted": _client(rating=_NUM),
    "organization_dashboard_viewed": _client(),
    "organization_switched": _client(),
    "organization_student_opened": _client(),
    "learning_profile_viewed": _client(),
    "curriculum_graph_viewed": _client(subjectId=_STR),
    "curriculum_topic_selected": _client(subjectId=_STR, topicId=_STR),
    "weak_point_diagnosis_viewed": _client(),
    "learning_operations_dashboard_viewed": _client(subjectId=_STR),
    "teacher_assignment_board_viewed": _client(),
    "teacher_assignment_suggested_clicked": _client(),
    "parent_monthly_report_viewed": _client(),
    "advanced_analytics_viewed": _client(),
    "retention_page_viewed": _client(),
    "partnership_page_viewed": _client(),
    "partnership_interest_submitted": _client(),
    # New web client events (card 134).
    "page_viewed": _client(route=_ROUTE, load_ms=_NUM),
    "web_vitals": _client(route=_ROUTE, lcp=_NUM, inp=_NUM, cls=_NUM),
    # Recorded by the backend.
    "question_asked": _server(subject=_STR, voice=_BOOL, has_image=_BOOL),
    "ai_answered": _server(latency_ms=_NUM, refused=_BOOL),
    "help_escalated": _server(wait_ms=_NUM),
    "teacher_replied": _server(response_ms=_NUM),
    "exercise_answered": _server(exercise_id=Prop("str", 128), correct=_BOOL, duration_ms=_NUM),
    "frontend_error": _server(
        route=_ROUTE,
        message_hash=Prop("str", 12),
        release=_STR,
        message=Prop("str", 200),
        name=_STR,
        source=Prop("str", 32),
        stack=Prop("str", 2400),
    ),
}

CLIENT_EVENTS = frozenset(name for name, spec in EVENTS.items() if spec.source == CLIENT)
SERVER_EVENTS = frozenset(name for name, spec in EVENTS.items() if spec.source == SERVER)

_NUM_LIMIT = 10**12


def _clean(value: Any, prop: Prop) -> Any:
    if prop.kind == "bool":
        return value if isinstance(value, bool) else None
    if prop.kind == "num":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if abs(value) > _NUM_LIMIT:
            return None
        return value if isinstance(value, int) else Decimal(str(round(value, 4)))
    if isinstance(value, str):
        return value[: prop.max_length]
    return None


def clean_props(name: str, props: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The storable props of event `name`, or `None` when the event is not listed.

    Unlisted keys, values of the wrong type and `None` are left out; strings
    are cut to their limit.
    """
    spec = EVENTS.get(name)
    if spec is None:
        return None
    cleaned: dict[str, Any] = {}
    for key, value in (props or {}).items():
        prop = spec.props.get(key)
        if prop is None or value is None:
            continue
        safe = _clean(value, prop)
        if safe is not None:
            cleaned[key] = safe
    return cleaned
