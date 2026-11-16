"""#467: entering a help request's classroom - whiteboard and voice credentials.

The routes, the help request and the teacher policy are the real ones, over
the shared table double of test_chat_help_request_lifecycle.py. Daily is a
recording double: no test reaches the network.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

from fakes.dynamodb import FakeTable
import httpx
from jose import jwt
import pytest

import test_chat_help_request_lifecycle as lifecycle
from test_chat_help_request_lifecycle import (
    CONV,
    HELP_KEY,
    OTHER_TEACHER,
    STUDENT,
    TEACHER,
    _client,
    _dispatch_to,
    _help,
    _set_status,
    _student_client,
)
from rule_violation_helpers import assert_violation
from stoa import config
from stoa.services import classroom, help_requests
from stoa.services.classroom import ClassroomErrorCode

SECRET = "wbo-test-secret-not-a-real-one"
WBO = "https://board.example.test"
ROOM = f"stoa-help-{CONV}"
ROOM_URL = f"https://stoa.daily.co/{ROOM}"
HelpCode = help_requests.HelpRequestErrorCode


class FakeDaily:
    """Daily's rooms and meeting tokens, in memory, with every call kept."""

    def __init__(self) -> None:
        self.rooms: dict[str, dict] = {}
        self.calls: list[tuple[str, str, dict | None]] = []
        self.fail_with: int | None = None
        self.raise_error: Exception | None = None

    def request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if self.raise_error is not None:
            raise self.raise_error
        if self.fail_with is not None:
            return self.fail_with, {"error": "server-error"}
        if path == "/meeting-tokens":
            return 200, {"token": f"daily-token-{len(self.calls)}"}
        if method == "POST" and path == "/rooms":
            name = body["name"]
            if name in self.rooms:
                return 400, {"error": "invalid-request-error"}
            self.rooms[name] = {
                "name": name,
                "url": f"https://stoa.daily.co/{name}",
                "privacy": body["privacy"],
                "config": dict(body["properties"]),
            }
            return 200, self.rooms[name]
        name = path.removeprefix("/rooms/")
        if name not in self.rooms:
            return 404, {"error": "not-found"}
        if method == "POST":
            self.rooms[name]["config"].update(body["properties"])
        return 200, self.rooms[name]

    def tokens(self) -> list[dict]:
        return [body["properties"] for _, path, body in self.calls if path == "/meeting-tokens"]


@pytest.fixture
def table(monkeypatch) -> FakeTable:
    built = lifecycle.build_table(monkeypatch)
    lifecycle.keep_waiting(monkeypatch)
    built.rows[(f"USER#{STUDENT}", "PROFILE")]["name"] = "Mia"
    built.rows[(f"USER#{TEACHER}", "PROFILE")]["name"] = "Herr Keller"
    return built


@pytest.fixture
def daily(monkeypatch) -> FakeDaily:
    fake = FakeDaily()
    monkeypatch.setattr(classroom, "HttpDailyClient", lambda api_key: fake)
    return fake


@pytest.fixture(autouse=True)
def configured(table) -> None:
    _configure()


def _configure(**overrides: str) -> None:
    values = {"wbo_base_url": WBO, "wbo_auth_secret": SECRET, "daily_api_key": "daily-test-key"}
    config.install(config.settings().model_copy(update={**values, **overrides}))


def _taken(table: FakeTable, teacher_id: str = TEACHER) -> None:
    _dispatch_to(table, teacher_id)
    assert _set_status(_client(teacher_id), "in_progress").status_code == 200


def _student_enters():
    return _student_client().post(f"/conversations/{CONV}/classroom")


def _teacher_enters(teacher_id: str = TEACHER):
    return _client(teacher_id).post(f"/teachers/me/help-requests/{CONV}/classroom")


def _board_token(entry: dict) -> str:
    parts = urlsplit(entry["whiteboardUrl"])
    assert f"{parts.scheme}://{parts.netloc}" == WBO
    assert parts.path == f"/boards/help-{CONV}"
    return parse_qs(parts.query)["token"][0]


# --- The student ---


@pytest.mark.parametrize("taken", [False, True], ids=["pending", "in_progress"])
def test_the_student_enters_while_the_request_is_open(table, daily, taken):
    if taken:
        _taken(table)
    response = _student_enters()
    assert response.status_code == 200, response.text
    entry = response.json()
    assert set(entry) == {"whiteboardUrl", "voice", "expiresAt"}
    assert set(entry["voice"]) == {"roomUrl", "token"}
    assert entry["voice"]["roomUrl"] == ROOM_URL
    assert entry["voice"]["token"].startswith("daily-token-")
    claims = jwt.decode(_board_token(entry), SECRET, algorithms=["HS256"])
    assert claims["roles"] == [f"editor:help-{CONV}"]
    assert claims["exp"] == int(datetime.fromisoformat(entry["expiresAt"]).timestamp())
    assert daily.tokens()[-1]["user_name"] == "Mia"


@pytest.mark.parametrize("ended", ["resolved", "withdrawn", "expired"])
def test_the_student_is_refused_once_the_request_has_ended(table, daily, ended):
    _help(table)["escalation_status"] = ended
    assert_violation(_student_enters(), HelpCode.TEACHER_HELP_REQUEST_CLOSED)
    assert daily.calls == []


def test_the_student_is_refused_when_no_teacher_was_asked(table, daily):
    del table.rows[HELP_KEY]
    assert_violation(_student_enters(), HelpCode.TEACHER_HELP_NOT_REQUESTED)
    assert daily.calls == []


# --- The teacher ---


def test_the_holding_teacher_enters_the_same_board_and_room_as_the_student(table, daily):
    _taken(table)
    teacher = _teacher_enters()
    assert teacher.status_code == 200, teacher.text
    student = _student_enters()
    assert student.status_code == 200, student.text

    for entry in (teacher.json(), student.json()):
        claims = jwt.decode(_board_token(entry), SECRET, algorithms=["HS256"])
        assert claims["roles"] == [f"editor:help-{CONV}"]
        assert entry["voice"]["roomUrl"] == ROOM_URL
    assert teacher.json()["voice"]["token"] != student.json()["voice"]["token"]
    assert [token["user_name"] for token in daily.tokens()] == ["Herr Keller", "Mia"]
    # One room, created once and reused.
    assert [call for call in daily.calls if call[:2] == ("POST", "/rooms")].__len__() == 1


def test_a_teacher_only_offered_the_request_is_refused(table, daily):
    _dispatch_to(table, TEACHER)
    assert_violation(
        _teacher_enters(), HelpCode.HELP_REQUEST_NOT_HELD, action="refresh_help_request"
    )
    assert daily.calls == []


def test_another_teacher_is_refused(table, daily):
    _taken(table)
    response = _teacher_enters(OTHER_TEACHER)
    assert response.status_code == 404, response.text
    assert daily.calls == []


def test_the_holding_teacher_is_refused_once_the_request_is_resolved(table, daily):
    _taken(table)
    assert _set_status(_client(TEACHER), "resolved").status_code == 200
    assert_violation(_teacher_enters(), HelpCode.TEACHER_HELP_REQUEST_CLOSED)
    assert daily.calls == []


# --- Configuration and Daily ---


@pytest.mark.parametrize("missing", ["wbo_base_url", "wbo_auth_secret", "daily_api_key"])
def test_a_missing_setting_makes_the_classroom_unavailable(table, daily, missing):
    _configure(**{missing: ""})
    assert_violation(_student_enters(), ClassroomErrorCode.CLASSROOM_UNAVAILABLE)
    assert daily.calls == []


def test_daily_failing_makes_the_classroom_unavailable(table, daily):
    daily.fail_with = 500
    assert_violation(_student_enters(), ClassroomErrorCode.CLASSROOM_UNAVAILABLE)


def test_daily_unreachable_makes_the_classroom_unavailable(table, daily):
    daily.raise_error = httpx.ConnectTimeout("timed out")
    assert_violation(_student_enters(), ClassroomErrorCode.CLASSROOM_UNAVAILABLE)


NOW = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def _settings() -> config.Settings:
    return config.settings()


def test_a_new_room_is_private_audio_first_and_expires_with_the_credentials():
    fake = FakeDaily()
    entry = classroom.enter(CONV, user_name="Mia", now=NOW, settings=_settings(), daily=fake)
    expiry = int((NOW + timedelta(hours=3)).timestamp())
    assert entry.expires_at == NOW + timedelta(hours=3)
    room = fake.rooms[ROOM]
    assert room["privacy"] == "private"
    assert room["config"]["exp"] == expiry
    assert room["config"]["eject_at_room_exp"] is True
    assert room["config"]["start_video_off"] is True
    assert room["config"]["enable_screenshare"] is False
    token = fake.tokens()[0]
    assert token == {
        "room_name": ROOM,
        "user_name": "Mia",
        "exp": expiry,
        "eject_at_token_exp": True,
        "start_video_off": True,
        "permissions": {"canSend": ["audio"]},
    }


def test_reentering_later_reuses_the_room_and_pushes_its_expiry_out():
    fake = FakeDaily()
    classroom.enter(CONV, user_name="Mia", now=NOW, settings=_settings(), daily=fake)
    later = NOW + timedelta(hours=1)
    classroom.enter(CONV, user_name="Mia", now=later, settings=_settings(), daily=fake)
    assert fake.rooms[ROOM]["config"]["exp"] == int((later + timedelta(hours=3)).timestamp())
    assert [call[:2] for call in fake.calls].count(("POST", "/rooms")) == 1


def test_an_earlier_entry_never_shortens_the_rooms_expiry():
    fake = FakeDaily()
    classroom.enter(CONV, user_name="Mia", now=NOW, settings=_settings(), daily=fake)
    calls = len(fake.calls)
    classroom.enter(CONV, user_name="Mia", now=NOW - timedelta(minutes=5), settings=_settings(), daily=fake)
    assert fake.rooms[ROOM]["config"]["exp"] == int((NOW + timedelta(hours=3)).timestamp())
    # Read the room, sign a token: no update.
    assert [call[:2] for call in fake.calls[calls:]] == [
        ("GET", f"/rooms/{ROOM}"),
        ("POST", "/meeting-tokens"),
    ]


def test_the_whiteboard_token_is_hs256_for_this_board_only():
    token = classroom.whiteboard_token(CONV, secret=SECRET, expires_at=NOW)
    assert jwt.get_unverified_header(token)["alg"] == "HS256"
    claims = jwt.get_unverified_claims(token)
    assert claims == {"roles": [f"editor:help-{CONV}"], "exp": int(NOW.timestamp())}
