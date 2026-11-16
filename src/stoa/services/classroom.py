"""虚拟课堂: the credentials that let a help request's student and teacher in (#467).

One classroom belongs to one help request, so it is named by the request's id,
which is the conversation's. It is a shared whiteboard (a self-hosted WBO) and
an audio-only Daily room. This module only issues the credentials for both;
who may enter is decided by `help_requests` (`admit_student_to_classroom`,
`admit_teacher_to_classroom`) before it is called.

- Whiteboard: WBO checks a JWT in the board URL's `token` query parameter with
  the same secret as its `AUTH_SECRET_KEY` (`server/auth/board_jwt.mjs`:
  `jsonwebtoken.verify(token, secret)`, HMAC, `exp` enforced). The `roles`
  claim is a list of `"<role>:<board>"`; `editor:help-<id>` lets the holder
  draw on that board and nowhere else. A token without `roles` would be an
  editor of every board, so it is always present. Board names must already be
  canonical in WBO (lower case, letters, digits, `-_~()`), which a uuid is.
- Voice: a private Daily room `stoa-help-<id>`, created on first entry and
  reused after, its expiry pushed out to the latest credential, plus a meeting
  token for the caller that may only send audio.

Missing configuration, or Daily failing, is `classroom_unavailable` (503); the
rest of the help request carries on without a classroom.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import quote

import httpx
from jose import jwt

from stoa import config
from stoa.db.repositories import user_repo
from stoa.rule_violation import RuleContract, RuleViolation, register_codes

logger = logging.getLogger(__name__)

CREDENTIAL_LIFETIME = timedelta(hours=3)
DAILY_API_BASE_URL = "https://api.daily.co/v1"
_DAILY_TIMEOUT = httpx.Timeout(connect=3.0, read=5.0, write=5.0, pool=3.0)


class ClassroomErrorCode(StrEnum):
    CLASSROOM_UNAVAILABLE = "classroom_unavailable"

    @property
    def contract(self) -> RuleContract:
        return CLASSROOM_ERROR_REGISTRY[self]


# Each code's message is the catalog's `error.<code>`
# (`stoa.services.message_catalog.errors.classroom`).
CLASSROOM_ERROR_REGISTRY: dict[ClassroomErrorCode, RuleContract] = {
    ClassroomErrorCode.CLASSROOM_UNAVAILABLE: RuleContract(
        503, "retry_later", retryable=True, max_attempts=1
    ),
}

register_codes("classroom", ClassroomErrorCode, CLASSROOM_ERROR_REGISTRY)


class ClassroomUnavailable(RuleViolation):
    """The classroom cannot be entered now: not configured, or Daily failed."""

    def __init__(self, detail: str = "") -> None:
        super().__init__(
            ClassroomErrorCode.CLASSROOM_UNAVAILABLE, internal_detail=detail or None
        )


# ── Daily ────────────────────────────────────────────────────────────────────


class DailyClient(Protocol):
    """One call to Daily's REST API: the status and the JSON body (or `{}`)."""

    def request(
        self, method: str, path: str, body: Mapping[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]: ...


class HttpDailyClient:
    """Daily over HTTPS, with the API key as a bearer token."""

    def __init__(self, api_key: str, *, base_url: str = DAILY_API_BASE_URL) -> None:
        self._api_key = api_key
        self._base_url = base_url

    def request(
        self, method: str, path: str, body: Mapping[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        with httpx.Client(
            base_url=self._base_url,
            timeout=_DAILY_TIMEOUT,
            headers={"Authorization": f"Bearer {self._api_key}"},
        ) as client:
            response = client.request(method, path, json=dict(body) if body is not None else None)
        try:
            parsed = response.json()
        except ValueError:
            parsed = {}
        return response.status_code, parsed if isinstance(parsed, dict) else {}


# ── Credentials ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClassroomCredentials:
    whiteboard_url: str
    voice_room_url: str
    voice_token: str
    expires_at: datetime


def display_name(user_id: str, *, fallback: str) -> str:
    """What the other person in the room sees: the account's name, never its email."""
    profile = user_repo.get_user(user_id) or {}
    name = profile.get("name")
    return name.strip() if isinstance(name, str) and name.strip() else fallback


def board_name(request_id: str) -> str:
    return f"help-{request_id}".lower()


def room_name(request_id: str) -> str:
    return f"stoa-help-{request_id}".lower()


def whiteboard_token(request_id: str, *, secret: str, expires_at: datetime) -> str:
    """A WBO token that lets its bearer edit this request's board, until `expires_at`."""
    claims = {"roles": [f"editor:{board_name(request_id)}"], "exp": int(expires_at.timestamp())}
    return jwt.encode(claims, secret, algorithm="HS256")


def enter(
    request_id: str,
    *,
    user_name: str,
    now: datetime | None = None,
    settings: config.Settings | None = None,
    daily: DailyClient | None = None,
) -> ClassroomCredentials:
    """The caller's credentials for the request's classroom.

    The caller has already been admitted by `help_requests`. Every entry
    issues fresh credentials valid for `CREDENTIAL_LIFETIME`.
    """
    current = settings or config.settings()
    base_url = current.wbo_base_url.strip().rstrip("/")
    secret = current.wbo_auth_secret
    api_key = current.daily_api_key.strip()
    if not (base_url and secret and api_key):
        raise ClassroomUnavailable("classroom not configured")

    issued_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(microsecond=0)
    expires_at = issued_at + CREDENTIAL_LIFETIME
    expiry = int(expires_at.timestamp())

    token = whiteboard_token(request_id, secret=secret, expires_at=expires_at)
    whiteboard_url = f"{base_url}/boards/{quote(board_name(request_id))}?token={token}"

    client = daily or HttpDailyClient(api_key)
    try:
        voice_room_url = _room(client, room_name(request_id), expiry)
        voice_token = _meeting_token(client, room_name(request_id), user_name, expiry)
    except httpx.HTTPError as exc:
        raise ClassroomUnavailable(f"daily unreachable: {type(exc).__name__}") from exc
    return ClassroomCredentials(whiteboard_url, voice_room_url, voice_token, expires_at)


def _room(client: DailyClient, name: str, expiry: int) -> str:
    """The room's URL, creating the room or pushing its expiry out to `expiry`."""
    status, room = client.request("GET", f"/rooms/{name}")
    if status == 404:
        status, room = client.request(
            "POST",
            "/rooms",
            {
                "name": name,
                "privacy": "private",
                "properties": {
                    "exp": expiry,
                    "eject_at_room_exp": True,
                    "start_video_off": True,
                    "enable_screenshare": False,
                    "enable_chat": False,
                },
            },
        )
        if status != 200:
            # Someone else may have created it between the read and the write.
            status, room = client.request("GET", f"/rooms/{name}")
    if status != 200:
        raise ClassroomUnavailable(f"daily room read failed: {status}")
    current_exp = _int((room.get("config") or {}).get("exp"))
    if current_exp is None or current_exp < expiry:
        status, updated = client.request("POST", f"/rooms/{name}", {"properties": {"exp": expiry}})
        if status != 200:
            raise ClassroomUnavailable(f"daily room update failed: {status}")
        room = updated or room
    url = room.get("url")
    if not isinstance(url, str) or not url:
        raise ClassroomUnavailable("daily room without url")
    return url


def _meeting_token(client: DailyClient, room: str, user_name: str, expiry: int) -> str:
    status, body = client.request(
        "POST",
        "/meeting-tokens",
        {
            "properties": {
                "room_name": room,
                "user_name": user_name,
                "exp": expiry,
                "eject_at_token_exp": True,
                "start_video_off": True,
                "permissions": {"canSend": ["audio"]},
            }
        },
    )
    token = body.get("token")
    if status != 200 or not isinstance(token, str) or not token:
        raise ClassroomUnavailable(f"daily meeting token failed: {status}")
    return token


def _int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
