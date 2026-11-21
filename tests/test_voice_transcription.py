"""#477: a student's recording turned into text by Voxtral, kept nowhere.

`POST /students/me/voice-questions/transcriptions` takes the recording as the
body. Refused without the model being asked while the parent's switch is off or
no parent is linked, for a recording that is not 16 kHz mono 16-bit PCM WAV
(the only format Voxtral takes of what a client can send, #542), over 2 MiB or
over 60 seconds, and past the day's allowance. What Voxtral is
sent is the recording and the transcription prompt, nothing more (ADR-010); the
recording is found in no table row, no table request, no log line and no
response besides the transcription.
"""

from __future__ import annotations

import base64
import json
import logging
import struct
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

import pytest
from botocore.exceptions import ReadTimeoutError
from fastapi import FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from fakes import recordings
from fakes.converse import FakeConverse, client_error
from fakes.dynamodb import FakeTable
from stoa import aws, config
from stoa.db import table as db_table
from stoa.db.repositories import user_repo, voice_question_consent_repo
from stoa.db.repositories import voice_transcription_usage_repo as usage_repo
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.routers import students
from stoa.security.authorization import CurrentAuthorizationFactRepository
from stoa.security.declared_authorization import get_authorization_fact_repository
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.services import transcription, voice_audio, voice_questions, voice_transcription

STUDENT = "student-voice"
PATH = "/students/me/voice-questions/transcriptions"
NOW = datetime(2026, 11, 17, 9, 30, tzinfo=UTC)
DAY = "2026-11-17"
MARKER = b"SECRET-CHILD-VOICE-MARKER-477"


# ── Fixtures ─────────────────────────────────────────────────────────────────


ACCOUNTS = {
    user_id: {
        "user_id": user_id,
        "role": role,
        "account_status": "active",
        "email": f"{user_id}@stoa.test",
        "name": user_id,
        "date_of_birth": "2014-01-01",
    }
    for user_id, role in ((STUDENT, "student"), ("parent-1", "parent"))
}


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(
        user_repo, "get_user", lambda user_id, **_kwargs: deepcopy(ACCOUNTS.get(user_id))
    )
    fake = FakeTable()
    fake.seed(
        {
            "PK": f"USER#{STUDENT}",
            "SK": "ACCOUNT_FENCE",
            "entity_type": "account_fence",
            "status": "active",
            "generation": 1,
        }
    )
    db_table.install(fake)
    return fake


@pytest.fixture
def voxtral():
    fake = FakeConverse()
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: fake})
    return fake


@pytest.fixture
def allowed(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The parent's switch on, with a parent linked (the switch's own tests are #476's)."""
    asked: list[str] = []

    def _allowed(student_id: str, **_kwargs: Any) -> bool:
        asked.append(student_id)
        return True

    monkeypatch.setattr(voice_questions, "allowed_for_student", _allowed)
    return asked


def _client(user_id: str = STUDENT, role: CanonicalRole = CanonicalRole.STUDENT) -> TestClient:
    actor = Actor(
        user_id, "https://identity.test", f"{user_id}-subject", role, AccountStatus.ACTIVE, role.value
    )
    app = FastAPI()
    app.include_router(students.router, prefix="/students")
    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_authorization_fact_repository] = CurrentAuthorizationFactRepository
    app.dependency_overrides[get_authorization_audit_sink] = MemoryAuthorizationAuditSink
    return TestClient(app)


def _post(audio: bytes, content_type: str = "audio/wav", **kwargs: Any):
    return _client(**kwargs).post(PATH, content=audio, headers={"Content-Type": content_type})


def _code(response) -> str:
    return response.json()["detail"]["code"]


def _count() -> int:
    return usage_repo.count(STUDENT, datetime.now(UTC).date().isoformat())


# ── The switch ───────────────────────────────────────────────────────────────


def test_switch_never_set_is_refused_without_asking_the_model(table, voxtral) -> None:
    response = _post(recordings.wav(5))

    assert response.status_code == 403
    assert _code(response) == "voice_questions_not_allowed"
    assert voxtral.requests == []
    assert _count() == 0


def test_switch_on_without_a_linked_parent_is_refused_without_asking_the_model(
    table, voxtral
) -> None:
    table.seed(
        {
            **voice_question_consent_repo.state_key(STUDENT),
            "entity_type": voice_question_consent_repo.ENTITY_TYPE,
            "student_id": STUDENT,
            "allowed": True,
            "changed_by": "parent-gone",
            "changed_at": "2026-11-16T10:00:00+00:00",
        }
    )

    response = _post(recordings.wav(5))

    assert response.status_code == 403
    assert _code(response) == "voice_questions_not_allowed"
    assert voxtral.requests == []


def test_switch_is_checked_before_the_recording_is_read(table, voxtral) -> None:
    """Off, even a recording that would be refused on its own answers 'not allowed'."""
    response = _post(b"not audio at all", "text/plain")

    assert _code(response) == "voice_questions_not_allowed"
    assert voxtral.requests == []


def test_only_a_student_account_may_transcribe(table, voxtral, allowed) -> None:
    response = _post(recordings.wav(5), user_id="parent-1", role=CanonicalRole.PARENT)

    assert response.status_code == 403
    assert voxtral.requests == []


# ── Formats ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "content_type", ["audio/wav", "audio/wave", "audio/x-wav", "audio/vnd.wave", "audio/WAV; codecs=1"]
)
def test_a_wav_recording_is_transcribed_and_sent_as_wav(
    table, voxtral, allowed, content_type: str
) -> None:
    audio = recordings.wav(12)
    response = _post(audio, content_type)

    assert response.status_code == 200, response.text
    assert response.json() == {"text": "Wie rechne ich 3 mal 4?"}
    [request] = voxtral.requests
    block = request["messages"][0]["content"][0]["audio"]
    assert block == {"format": "wav", "source": {"bytes": audio}}
    assert _count() == 1


def test_the_model_is_only_ever_sent_a_format_it_takes() -> None:
    """Voxtral takes mp3 and wav and refuses the rest (#542): nothing else can be sent."""
    assert {container.value for container in voice_audio.Container} <= {"wav", "mp3"}


@pytest.mark.parametrize(
    ("audio", "content_type"),
    [
        # What a browser's MediaRecorder writes: the model refuses all three.
        (recordings.webm(5), "audio/webm;codecs=opus"),
        (recordings.ogg(5), "audio/ogg;codecs=opus"),
        (recordings.mp4(5), "audio/mp4"),
        (b"ID3\x04" + b"\x00" * 64, "audio/mpeg"),
        (recordings.webm(5), "audio/wav"),  # declared WAV, sent another
        (recordings.wav(5), "audio/webm"),  # declared another, sent WAV
        (recordings.wav(5), "application/octet-stream"),
        (recordings.wav(5), ""),
        # A WAV, but not the one layout taken.
        (recordings.wav(5, rate=44_100), "audio/wav"),
        (recordings.wav(5, rate=48_000), "audio/wav"),
        (recordings.wav(5, channels=2), "audio/wav"),
        (recordings.wav(5, bits=8), "audio/wav"),
        (recordings.wav(5, bits=32, tag=3), "audio/wav"),  # float samples
        (recordings.wav(5, tag=0xFFFE), "audio/wav"),  # WAVE_FORMAT_EXTENSIBLE
    ],
    ids=[
        "chrome-webm", "firefox-ogg", "safari-mp4", "mp3", "webm-as-wav", "wav-as-webm",
        "octet-stream", "no-type", "44k", "48k", "stereo", "8-bit", "float", "extensible",
    ],
)
def test_other_formats_are_unsupported_without_asking_the_model(
    table, voxtral, allowed, audio: bytes, content_type: str
) -> None:
    response = _post(audio, content_type)

    assert response.status_code == 415
    assert _code(response) == "voice_recording_unsupported"
    assert "Retry-After" not in response.headers
    assert voxtral.requests == []
    assert _count() == 0


def _cut_data_chunk(audio: bytes) -> bytes:
    return audio[: audio.index(b"data") + 8 + 100]


def _data_first(audio: bytes) -> bytes:
    fmt_at, data_at = audio.index(b"fmt "), audio.index(b"data")
    return audio[:fmt_at] + audio[data_at:] + audio[fmt_at:data_at]


@pytest.mark.parametrize(
    ("audio", "content_type"),
    [
        (_cut_data_chunk(recordings.wav(5)), "audio/wav"),
        (recordings.wav(5)[:30], "audio/wav"),  # inside the fmt chunk
        (recordings.wav(5)[:36], "audio/wav"),  # fmt, no data chunk
        (_data_first(recordings.wav(5)), "audio/wav"),
        (recordings.wav(0), "audio/wav"),
        (recordings.wav(5)[:-1], "audio/wav"),  # the data chunk runs past the end
        (b"", "audio/wav"),
    ],
    ids=["data-cut", "fmt-cut", "no-data", "data-before-fmt", "no-samples", "short-end", "empty"],
)
def test_a_recording_whose_length_cannot_be_read_is_refused(
    table, voxtral, allowed, audio: bytes, content_type: str
) -> None:
    response = _post(audio, content_type)

    assert response.status_code == 422
    assert _code(response) == "voice_recording_unreadable"
    assert voxtral.requests == []


def test_a_wav_with_chunks_besides_fmt_and_data_is_read() -> None:
    odd = b"LIST" + struct.pack("<I", 3) + b"abc" + b"\x00"  # an odd size, padded
    recording = voice_audio.read(recordings.wav(4, extra_chunk=odd), "audio/wav")

    assert recording.seconds == pytest.approx(4)


# ── Length and size ──────────────────────────────────────────────────────────


def test_a_minute_is_taken_and_longer_is_refused(table, voxtral, allowed) -> None:
    minute = recordings.wav(60)
    assert len(minute) < voice_transcription.MAX_BYTES
    assert _post(minute).status_code == 200

    response = _post(recordings.wav(62))

    assert response.status_code == 422
    assert _code(response) == "voice_recording_too_long"
    assert "60" in response.json()["detail"]["message"]
    assert len(voxtral.requests) == 1


def test_a_recording_over_two_mebibytes_is_refused(table, voxtral, allowed) -> None:
    audio = recordings.wav(70)
    assert len(audio) > voice_transcription.MAX_BYTES

    response = _post(audio)

    assert response.status_code == 413
    assert _code(response) == "voice_recording_too_large"
    assert voxtral.requests == []
    assert _count() == 0


def test_size_is_judged_by_the_bytes_not_only_the_declared_length() -> None:
    with pytest.raises(voice_transcription.VoiceQuestionViolation) as refused:
        voice_transcription.check_recording(
            b"\x00" * (voice_transcription.MAX_BYTES + 1), "audio/wav", declared_length=10
        )
    assert refused.value.code is voice_transcription.VoiceQuestionErrorCode.VOICE_RECORDING_TOO_LARGE


# ── The day's allowance ──────────────────────────────────────────────────────


def test_past_the_daily_limit_the_model_is_not_asked(table, voxtral, allowed) -> None:
    config.install(config.settings().model_copy(update={"voice_transcription_daily_limit": 2}))

    assert _post(recordings.wav(5)).status_code == 200
    assert _post(recordings.wav(5)).status_code == 200
    response = _post(recordings.wav(5))

    assert response.status_code == 429
    assert _code(response) == "voice_transcription_daily_limit"
    assert "2" in response.json()["detail"]["message"]
    assert len(voxtral.requests) == 2
    assert _count() == 2


def test_the_counter_is_per_utc_day_and_expires(table, voxtral, allowed) -> None:
    voice_transcription.transcribe(STUDENT, recordings.wav(5), "audio/wav", now=NOW)
    voice_transcription.transcribe(
        STUDENT, recordings.wav(5), "audio/wav", now=datetime(2026, 11, 18, 0, 1, tzinfo=UTC)
    )

    assert usage_repo.count(STUDENT, DAY) == 1
    assert usage_repo.count(STUDENT, "2026-11-18") == 1
    row = table.rows[(f"STUDENT#{STUDENT}", f"VOICE_TRANSCRIPTIONS_DAY#{DAY}")]
    assert row["student_id"] == STUDENT
    assert "created_at" not in row
    # A day after the day ends.
    assert int(row["expires_at"]) == int(datetime(2026, 11, 19, tzinfo=UTC).timestamp())


def test_an_account_being_deleted_is_not_counted_or_transcribed(table, voxtral, allowed) -> None:
    table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")]["status"] = "deleting"

    response = _post(recordings.wav(5))

    assert response.status_code == 403
    assert voxtral.requests == []


# ── The model failing ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "failure",
    [
        client_error("ThrottlingException"),
        client_error("ServiceUnavailableException"),
        client_error("ModelTimeoutException"),
        ReadTimeoutError(endpoint_url="https://bedrock-runtime.eu-west-1.amazonaws.com"),
    ],
    ids=["throttled", "unavailable", "timeout", "read-timeout"],
)
def test_a_model_failure_is_retryable_and_not_counted(table, allowed, failure) -> None:
    voxtral = FakeConverse(failure)
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: voxtral})
    response = _post(recordings.wav(5))

    assert response.status_code == 503
    assert _code(response) == "voice_transcription_unavailable"
    assert response.headers["Retry-After"] == "5"
    assert len(voxtral.requests) == 1
    assert _count() == 0


@pytest.mark.parametrize(
    "refusal",
    [
        client_error(
            "ValidationException",
            "This model doesn't support the audio format that you provided for user messages.",
        ),
        client_error("AccessDeniedException"),
    ],
    ids=["format-refused", "denied"],
)
def test_a_model_refusal_is_not_retryable_and_not_counted(table, allowed, refusal) -> None:
    """Sending it again cannot help: the student is told to type, and nothing invites a retry."""
    voxtral = FakeConverse(refusal)
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: voxtral})
    response = _post(recordings.wav(5))

    assert response.status_code == 502
    assert _code(response) == "voice_transcription_refused"
    assert "Retry-After" not in response.headers
    contract = voice_transcription.VoiceQuestionErrorCode.VOICE_TRANSCRIPTION_REFUSED.contract
    assert (contract.retryable, contract.action, contract.max_attempts) == (False, None, 0)
    assert len(voxtral.requests) == 1
    assert _count() == 0


def test_a_refused_audio_is_logged_for_the_alarm(
    table, allowed, caplog: pytest.LogCaptureFixture
) -> None:
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: FakeConverse(client_error("ValidationException"))})
    with caplog.at_level(logging.WARNING, logger="stoa.services.transcription"):
        _post(recordings.wav(5))

    [record] = [r for r in caplog.records if r.name == "stoa.services.transcription"]
    assert record.event == "voice_transcription_refused"
    assert record.provider_error_code == "ValidationException"
    assert record.provider_request_id == "ValidationException-request"


@pytest.mark.parametrize(
    ("code", "event"),
    [
        # What Bedrock answered on the account (2026-11-20): every voice question
        # would fail this way until someone changes something, so these page.
        ("ValidationException", "voice_transcription_refused"),
        ("AccessDeniedException", "voice_transcription_refused"),
        # These heal on their own; the student is told to try again.
        ("ThrottlingException", "voice_transcription_failed"),
        ("ServiceUnavailableException", "voice_transcription_failed"),
        ("ModelTimeoutException", "voice_transcription_failed"),
    ],
)
def test_only_a_refusal_writes_the_line_the_alarm_counts(
    table, allowed, caplog: pytest.LogCaptureFixture, code: str, event: str
) -> None:
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: FakeConverse(client_error(code))})
    with caplog.at_level(logging.WARNING, logger="stoa.services.transcription"):
        _post(recordings.wav(5))

    [record] = [r for r in caplog.records if r.name == "stoa.services.transcription"]
    assert record.event == event
    # stoa-infra's metric filter matches this phrase in the formatted line.
    assert ("voice transcription refused" in record.getMessage()) is (
        event == "voice_transcription_refused"
    )


def test_nothing_heard_is_its_own_refusal(table, allowed) -> None:
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: FakeConverse("   ")})
    response = _post(recordings.wav(5))

    assert response.status_code == 422
    assert _code(response) == "voice_recording_silent"
    assert _count() == 1  # the model was asked


def test_a_response_without_a_message_is_a_failure(table, allowed) -> None:
    class Broken(FakeConverse):
        def converse(self, **request: Any) -> dict[str, Any]:
            self.requests.append(request)
            return {"output": {}}

    aws.install({aws.Kind.VOICE_TRANSCRIPTION: Broken()})
    response = _post(recordings.wav(5))

    assert response.status_code == 503
    assert _count() == 0


# ── What Voxtral is sent (ADR-010) ───────────────────────────────────────────


def test_voxtral_is_sent_the_recording_and_the_prompt_and_nothing_else(
    table, voxtral, allowed
) -> None:
    audio = recordings.wav(8, payload=MARKER)

    assert _post(audio).status_code == 200

    [request] = voxtral.requests
    assert request == {
        "modelId": "mistral.voxtral-small-24b-2507",
        "messages": [
            {
                "role": "user",
                "content": [
                    {"audio": {"format": "wav", "source": {"bytes": audio}}},
                    {"text": transcription.PROMPT},
                ],
            }
        ],
        "inferenceConfig": {"maxTokens": transcription.MAX_TOKENS, "temperature": 0},
    }
    sent = json.dumps(request, default=lambda value: base64.b64encode(value).decode())
    assert STUDENT not in sent
    assert "system" not in request and "toolConfig" not in request
    assert "additionalModelRequestFields" not in request


def test_the_prompt_says_transcribe_verbatim_and_do_not_translate() -> None:
    prompt = transcription.PROMPT.lower()
    assert "exactly as it is spoken" in prompt
    assert "do not translate" in prompt
    assert "do not answer" in prompt


def test_voxtral_is_called_in_ireland_on_its_own_client(table, voxtral, allowed) -> None:
    _post(recordings.wav(5))

    kinds = {request.kind for request in aws.requests()}
    assert kinds == {aws.Kind.VOICE_TRANSCRIPTION}
    [request] = [r for r in aws.requests() if r.kind is aws.Kind.VOICE_TRANSCRIPTION]
    assert (request.service, request.region) == ("bedrock-runtime", "eu-west-1")
    assert request.config.read_timeout == 10


# ── The recording is kept nowhere ────────────────────────────────────────────


@contextmanager
def _every_log_line(caplog: pytest.LogCaptureFixture):
    """Every record at every level: `stoa` sets its own level, so it is lowered too."""
    with caplog.at_level(logging.DEBUG), caplog.at_level(logging.DEBUG, logger="stoa"):
        yield


def _everywhere_it_must_not_be(table: FakeTable, caplog: pytest.LogCaptureFixture) -> str:
    stored = repr(table.rows) + repr(table.requests)
    logged = "\n".join(
        record.getMessage() + repr(record.__dict__) for record in caplog.records
    )
    return stored + logged


@pytest.mark.parametrize(
    "outcome",
    [
        "Wie rechne ich 3 mal 4?",
        client_error("ValidationException", "could not decode audio"),
        client_error("ThrottlingException"),
        "",
    ],
    ids=["transcribed", "refused", "throttled", "silent"],
)
def test_the_recording_is_in_no_row_request_or_log(
    table, allowed, caplog: pytest.LogCaptureFixture, outcome
) -> None:
    voxtral = FakeConverse(outcome)
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: voxtral})
    audio = recordings.wav(5, payload=MARKER)
    with _every_log_line(caplog):
        response = _post(audio)

    assert voxtral.requests  # the model was asked, so the recording got as far as it could
    seen = _everywhere_it_must_not_be(table, caplog)
    for form in (MARKER, base64.b64encode(MARKER), audio[:64], base64.b64encode(audio)[:64]):
        text = form.decode("latin-1")
        assert text not in seen
        assert text not in response.text
    # Nothing but the voice counter (and its account registry) was written.
    written = {
        sk for (pk, sk) in table.rows if pk == f"STUDENT#{STUDENT}"
    }
    assert written <= {f"VOICE_TRANSCRIPTIONS_DAY#{datetime.now(UTC).date().isoformat()}"}
    # No other AWS client was asked for: no S3, no other Bedrock.
    assert {request.kind for request in aws.requests()} <= {aws.Kind.VOICE_TRANSCRIPTION}


def test_a_refused_recording_is_in_no_log_either(
    table, voxtral, allowed, caplog: pytest.LogCaptureFixture
) -> None:
    audio = recordings.wav(62, payload=MARKER)
    with _every_log_line(caplog):
        response = _post(audio)

    assert _code(response) == "voice_recording_too_long"
    assert MARKER.decode() not in _everywhere_it_must_not_be(table, caplog)


# ── The length, read from the recording ──────────────────────────────────────


@pytest.mark.parametrize("seconds", [0.5, 17.5, 59.98])
def test_the_length_is_read_from_the_data_chunk(seconds: float) -> None:
    recording = voice_audio.read(recordings.wav(seconds), "audio/wav")

    assert recording.container is voice_audio.Container.WAV
    assert recording.seconds == pytest.approx(seconds, abs=1 / 16_000)


def test_the_riff_size_is_not_trusted_for_the_length() -> None:
    audio = recordings.wav(3)
    lying = audio[:4] + struct.pack("<I", 0xFFFFFFFF) + audio[8:]

    assert voice_audio.read(lying, "audio/wav").seconds == pytest.approx(3)
