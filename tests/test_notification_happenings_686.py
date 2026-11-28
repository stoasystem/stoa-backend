"""What students, parents, teachers and admins get from each notification, recorded (#686).

Every kind of thing that notifies somebody - a teacher takes, answers or lets
lapse a help request, an offer is made, paused or closed, a moderation case is
opened or updated, a subscription request moves - is told once over the shared
table double, with every channel switched on: the bell row it stores, what the
realtime connections are sent, what the push provider is sent, the dispatch
reminder email SES gets, the only-once ledger's rows, and what each reader's
bell shows (in their own language). All of it is compared with
`fixtures/notification_happenings_686.json`.

The snapshot was taken from the code before notifications became one package
(#686); the move keeps it byte for byte. Timestamps are blanked. Moderation and
subscription notifications had a random id before #686, so in their scenarios
the id and everything derived from it (delivery ids) is blanked too; their new
fixed ids are held by `test_notification_retries_686.py`.

A change that is meant shows up here too. Regenerate the snapshot then, and
read its diff before committing it:

    STOA_WRITE_NOTIFICATION_SNAPSHOT=1 pytest tests/test_notification_happenings_686.py
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from urllib import request

import pytest
from fakes.dynamodb import FakeTable

from stoa import aws, config
from stoa.aws import Kind
from stoa.db import table as db_table
from stoa.db.repositories import account_deletion_repo, notification_repo, websocket_repo

import notification_happenings_686 as tell

SNAPSHOT = Path(__file__).parent / "fixtures" / "notification_happenings_686.json"
GENERATION = 4
PEOPLE = {
    tell.STUDENT: ("student", "de"),
    tell.TEACHER: ("teacher", "fr"),
    tell.PARENT: ("parent", "it"),
    tell.ADMIN: ("admin", "en"),
}
TEACHER_EMAIL = "teacher-686@stoa.test"
WEBSOCKET_ENDPOINT = "https://ws.stoa.test/live"
PUSH_ENDPOINT = "https://push.stoa.test/send"
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+00:00|Z)?")
_VOLATILE_KEYS = {"expires_at", "lease_expires_at", "sweep_due_at", "listed_at"}


class _Recorder:
    def __init__(self) -> None:
        self.ses: list[dict[str, Any]] = []
        self.posts: list[dict[str, Any]] = []
        self.pushes: list[dict[str, Any]] = []


class _Ses:
    def __init__(self, recorder: _Recorder) -> None:
        self._recorder = recorder

    def send_email(self, **kwargs: Any) -> dict[str, Any]:
        self._recorder.ses.append(kwargs)
        return {"MessageId": f"ses-{len(self._recorder.ses)}"}


class _Gateway:
    def __init__(self, recorder: _Recorder) -> None:
        self._recorder = recorder

    def post_to_connection(self, *, ConnectionId: str, Data: bytes) -> dict[str, Any]:
        self._recorder.posts.append(
            {"connection_id": ConnectionId, "data": json.loads(Data.decode("utf-8"))}
        )
        return {}


class _PushResponse:
    status = 202

    def __enter__(self) -> _PushResponse:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def read(self) -> bytes:
        return b'{"accepted":true}'


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[FakeTable, _Recorder]]:
    double = FakeTable()
    for user_id, (role, locale) in PEOPLE.items():
        double.seed(
            {
                **account_deletion_repo.account_fence_key(user_id),
                "entity_type": "account_fence",
                "status": "active",
                "generation": GENERATION,
            },
            {
                "PK": f"USER#{user_id}",
                "SK": "PROFILE",
                "user_id": user_id,
                "role": role,
                "preferred_locale": locale,
                "email": TEACHER_EMAIL if user_id == tell.TEACHER else f"{user_id}@stoa.test",
            },
        )
    db_table.install(double)
    recorder = _Recorder()
    aws.install(
        {
            Kind.SES_DISPATCH_REMINDER: _Ses(recorder),
            Kind.WEBSOCKET_MANAGEMENT: _Gateway(recorder),
        }
    )

    def urlopen(req: request.Request, timeout: float = 0) -> _PushResponse:
        recorder.pushes.append(
            {
                "url": req.full_url,
                "headers": dict(sorted(req.header_items())),
                "body": json.loads(bytes(req.data or b"").decode("utf-8")),
            }
        )
        return _PushResponse()

    monkeypatch.setattr(request, "urlopen", urlopen)
    config.install(
        config.settings().model_copy(
            update={
                "stoa_enable_best_effort_notifications": True,
                "websocket_api_endpoint": WEBSOCKET_ENDPOINT,
                "notification_push_provider": "fcm",
                "notification_push_provider_approved": True,
                "notification_push_template": "stoa-default",
                "notification_push_send_enabled": True,
                "notification_push_provider_endpoint_url": PUSH_ENDPOINT,
                "notification_push_provider_api_key": "push-key",
                "notification_email_sender": "STOA <noreply@stoa.test>",
            }
        )
    )
    for user_id, (role, _locale) in PEOPLE.items():
        tell.switch_push_on(user_id)
        tell.register_push_device(_actor(user_id), f"device-token-{user_id}")
        websocket_repo.put_connection(
            {
                "entity_type": websocket_repo.CONNECTION_ENTITY,
                "connection_id": f"conn-{user_id}",
                "user_id": user_id,
                "role": role,
                "subscribed_channels": sorted({f"user:{user_id}", f"role:{role}"}),
                "connected_at": "2026-11-28T08:00:00+00:00",
                "last_seen_at": "2026-11-28T08:00:00+00:00",
                "expires_at": 4_102_444_800,
                "endpoint_url": WEBSOCKET_ENDPOINT,
                "owner_id": user_id,
            }
        )
    try:
        yield double, recorder
    finally:
        db_table.install(None)
        aws.install(None)


def _actor(user_id: str) -> dict[str, str]:
    return {"sub": user_id, "role": PEOPLE[user_id][0]}


def _blank(value: Any, random_ids: list[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                "<time>"
                if key in _VOLATILE_KEYS and item is not None
                else _blank(item, random_ids)
            )
            for key, item in sorted(value.items())
        }
    if isinstance(value, (list, tuple)):
        return [_blank(item, random_ids) for item in value]
    if isinstance(value, str):
        text = _TIMESTAMP.sub("<time>", value)
        for event_id in random_ids:
            text = text.replace(event_id, "<event-id>")
        return text
    return value


def _derived_ids(table: FakeTable, random_ids: list[str]) -> list[str]:
    """The delivery ids digested from an id that was random before #686."""
    if not random_ids:
        return []
    derived: list[str] = []
    for row in table.rows.values():
        if row.get("entity_type") == notification_repo.DELIVERY_INTENT_ENTITY:
            derived.append(str(row.get("operation_id") or ""))
        for key in ("websocket_delivery_attempts", "push_delivery_attempts"):
            for attempt in (row.get("metadata") or {}).get(key) or []:
                derived.append(str(attempt.get("delivery_id") or ""))
    return [value for value in derived if value]


def _observed(table: FakeTable, recorder: _Recorder, *, random_ids: bool) -> dict[str, Any]:
    events = sorted(
        (
            dict(row)
            for row in table.rows.values()
            if row.get("entity_type") == notification_repo.NOTIFICATION_ENTITY
        ),
        key=lambda row: (str(row.get("event_type")), str(row.get("recipient_role"))),
    )
    ids = [str(row["event_id"]) for row in events] if random_ids else []
    ids = [*_derived_ids(table, ids), *ids]
    intents = sorted(
        (
            {
                "channel": row.get("channel"),
                "status": row.get("status"),
                "outcome_status": row.get("outcome_status"),
                "event_ids": row.get("event_ids"),
                "operation_id": row.get("operation_id"),
            }
            for row in table.rows.values()
            if row.get("entity_type") == notification_repo.DELIVERY_INTENT_ENTITY
        ),
        key=lambda row: (str(row["channel"]), str(row["operation_id"])),
    )
    bells = {
        user_id: tell.bell(_actor(user_id)) for user_id in PEOPLE
    }
    return _blank(
        {
            "events": events,
            "intents": intents,
            "realtime": sorted(recorder.posts, key=lambda post: post["connection_id"]),
            "push": recorder.pushes,
            "email": recorder.ses,
            "bells": bells,
        },
        ids,
    )


SCENARIOS: dict[str, tuple[Callable[[], None], bool]] = {
    "teacher_takes_text": (lambda: tell.teacher_took(mode="text"), False),
    "teacher_takes_classroom": (lambda: tell.teacher_took(mode="classroom"), False),
    "teacher_replies": (tell.teacher_replied, False),
    "request_expires_case_returned": (lambda: tell.request_expired(case_returned=True), False),
    "request_expires_case_kept": (lambda: tell.request_expired(case_returned=False), False),
    "help_offered": (lambda: tell.help_offered(standing=False), False),
    "help_offered_standing": (lambda: tell.help_offered(standing=True), False),
    "teacher_paused": (tell.teacher_paused, False),
    "offer_closed_expired": (lambda: tell.offer_closed("expired"), False),
    "offer_closed_reassigned": (lambda: tell.offer_closed("reassigned"), False),
    "offer_closed_withdrawn": (lambda: tell.offer_closed("withdrawn"), False),
    "moderation_case_opened": (tell.moderation_opened, True),
    "moderation_case_updated": (tell.moderation_updated, True),
    "moderation_case_updated_by_admin_report": (tell.moderation_updated_admin_report, True),
    "subscription_requested": (tell.subscription_requested, True),
    "subscription_request_approved": (tell.subscription_approved, True),
}


def _record() -> dict[str, Any]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.exists() else {}


@pytest.mark.parametrize("scenario", sorted(SCENARIOS))
def test_each_happening_reaches_every_channel_as_recorded(world, scenario: str) -> None:
    table, recorder = world
    happen, random_ids = SCENARIOS[scenario]

    happen()

    observed = json.loads(json.dumps(_observed(table, recorder, random_ids=random_ids), default=str))
    if os.environ.get("STOA_WRITE_NOTIFICATION_SNAPSHOT"):
        recorded = _record()
        recorded[scenario] = observed
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        with SNAPSHOT.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(recorded, handle, ensure_ascii=False, indent=1, sort_keys=True)
            handle.write("\n")
        return
    assert observed == _record()[scenario]


def test_every_scenario_is_recorded() -> None:
    assert set(_record()) == set(SCENARIOS)
