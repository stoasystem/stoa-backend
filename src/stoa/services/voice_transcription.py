"""A student's spoken question, turned into text (#477, part of #469).

The order is the rule:

1. The parent's switch (`voice_questions.allowed_for_student`): off, or no
   linked parent, and the request is refused before anything else is read.
2. The recording itself: a container the transcription takes (`voice_audio`),
   at most `MAX_BYTES`, at most `MAX_SECONDS` long by its own headers.
3. The day's allowance: one count per transcription, at most
   `voice_transcription_daily_limit` per UTC day. Taken before the model is
   asked, given back when the model fails.
4. The transcriber (`transcription.Transcriber`).

Steps 1 to 3 refuse without the model being asked. The recording is held in
memory for the length of this call and goes nowhere but the transcriber: not to
S3, not to the table, not to a log line or an exception message.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final

from stoa import config, log_facts
from stoa.db.repositories import voice_transcription_usage_repo as usage_repo
from stoa.rule_violation import RuleContract, RuleViolation, register_codes
from stoa.services import voice_audio, voice_questions
from stoa.services.transcription import Transcriber, TranscriptionFailed, VoxtralTranscriber

logger = log_facts.get_logger(__name__)

# A spoken question is meant to take under 30 seconds (#469); a minute leaves a
# child room to finish a sentence. The client stops recording there.
MAX_SECONDS: Final = 60
# A recording stopped at the minute ends on a whole audio frame (20 ms of Opus,
# 1024 samples of AAC), so it can read a little longer than it was.
_FRAME_SLACK_SECONDS: Final = 0.5
# Chrome records Opus and Safari AAC at up to 128 kbit/s: a minute is under
# 1 MB. 2 MiB is twice that, and stays far inside what reaches the function: a
# binary body comes base64-encoded, 4/3 of its size, inside the 6 MB Lambda
# request payload (HTTP API's own limit is 10 MB).
MAX_BYTES: Final = 2 * 1024 * 1024


# ── Errors ───────────────────────────────────────────────────────────────────


class VoiceQuestionErrorCode(StrEnum):
    """Why a recording was not transcribed; the strings are the client's (#211)."""

    VOICE_QUESTIONS_NOT_ALLOWED = "voice_questions_not_allowed"
    VOICE_RECORDING_UNSUPPORTED = "voice_recording_unsupported"
    VOICE_RECORDING_TOO_LARGE = "voice_recording_too_large"
    VOICE_RECORDING_TOO_LONG = "voice_recording_too_long"
    VOICE_RECORDING_UNREADABLE = "voice_recording_unreadable"
    VOICE_RECORDING_SILENT = "voice_recording_silent"
    VOICE_TRANSCRIPTION_DAILY_LIMIT = "voice_transcription_daily_limit"
    VOICE_TRANSCRIPTION_UNAVAILABLE = "voice_transcription_unavailable"

    @property
    def contract(self) -> RuleContract:
        return VOICE_QUESTION_ERROR_REGISTRY[self]


_Code = VoiceQuestionErrorCode

# Each code's message is the catalog's `error.<code>`
# (`stoa.services.message_catalog.errors.voice_question`).
VOICE_QUESTION_ERROR_REGISTRY: dict[VoiceQuestionErrorCode, RuleContract] = {
    # The client reads `GET /students/me/voice-questions` and hides the microphone.
    _Code.VOICE_QUESTIONS_NOT_ALLOWED: RuleContract(403),
    _Code.VOICE_RECORDING_UNSUPPORTED: RuleContract(415),
    _Code.VOICE_RECORDING_TOO_LARGE: RuleContract(413),
    _Code.VOICE_RECORDING_TOO_LONG: RuleContract(422),
    _Code.VOICE_RECORDING_UNREADABLE: RuleContract(422),
    # Nothing was heard; the attempt still counts, as the model was asked.
    _Code.VOICE_RECORDING_SILENT: RuleContract(422),
    _Code.VOICE_TRANSCRIPTION_DAILY_LIMIT: RuleContract(429, "retry_later"),
    # The model, or the counter, failed. Nothing was counted, so the same
    # recording may be sent again.
    _Code.VOICE_TRANSCRIPTION_UNAVAILABLE: RuleContract(
        503, "retry_later", retryable=True, max_attempts=1, retry_after_seconds=5
    ),
}

register_codes("voice_question", VoiceQuestionErrorCode, VOICE_QUESTION_ERROR_REGISTRY)


class VoiceQuestionViolation(RuleViolation):
    """A recording was refused; `code` says why."""

    def __init__(
        self,
        code: VoiceQuestionErrorCode,
        *,
        internal_detail: str | None = None,
        params: dict[str, object] | None = None,
    ) -> None:
        super().__init__(code, internal_detail=internal_detail, params=params)


# ── The transcription ────────────────────────────────────────────────────────


_transcriber: Transcriber | None = None


def transcriber() -> Transcriber:
    """The transcriber in use: Voxtral unless a test put its own (`use_transcriber`)."""
    global _transcriber
    if _transcriber is None:
        _transcriber = VoxtralTranscriber()
    return _transcriber


def use_transcriber(replacement: Transcriber | None) -> None:
    """Swap the transcriber; `None` goes back to Voxtral."""
    global _transcriber
    _transcriber = replacement


def _day(now: datetime) -> tuple[str, int]:
    """The UTC day of `now`, and when its counter may go (a day after it ends)."""
    day = now.astimezone(UTC).date()
    ends = datetime(day.year, day.month, day.day, tzinfo=UTC) + timedelta(days=1)
    return day.isoformat(), int((ends + timedelta(days=1)).timestamp())


def check_recording(
    audio: bytes, content_type: str | None, *, declared_length: int | None = None
) -> voice_audio.Recording:
    """The recording, if it is one the transcription takes; refused otherwise."""
    if (declared_length is not None and declared_length > MAX_BYTES) or len(audio) > MAX_BYTES:
        raise VoiceQuestionViolation(
            _Code.VOICE_RECORDING_TOO_LARGE, params={"max_megabytes": MAX_BYTES // (1024 * 1024)}
        )
    if not audio:
        raise VoiceQuestionViolation(_Code.VOICE_RECORDING_UNREADABLE, internal_detail="empty body")
    try:
        recording = voice_audio.read(audio, content_type)
    except voice_audio.UnsupportedFormat as exc:
        raise VoiceQuestionViolation(
            _Code.VOICE_RECORDING_UNSUPPORTED, internal_detail=str(exc)
        ) from None
    except voice_audio.Unreadable as exc:
        raise VoiceQuestionViolation(
            _Code.VOICE_RECORDING_UNREADABLE, internal_detail=str(exc)
        ) from None
    if recording.seconds > MAX_SECONDS + _FRAME_SLACK_SECONDS:
        raise VoiceQuestionViolation(
            _Code.VOICE_RECORDING_TOO_LONG, params={"max_seconds": MAX_SECONDS}
        )
    return recording


def transcribe(
    student_id: str,
    audio: bytes,
    content_type: str | None,
    *,
    declared_length: int | None = None,
    now: datetime | None = None,
    table: Any | None = None,
) -> str:
    """What the student said, in the language they said it in."""
    if not voice_questions.allowed_for_student(student_id, table=table):
        raise VoiceQuestionViolation(_Code.VOICE_QUESTIONS_NOT_ALLOWED)
    recording = check_recording(audio, content_type, declared_length=declared_length)

    limit = config.settings().voice_transcription_daily_limit
    day, expires_at = _day(now or datetime.now(UTC))
    try:
        usage_repo.admit(student_id, day, limit=limit, expires_at=expires_at, table=table)
    except usage_repo.DailyLimitReached:
        raise VoiceQuestionViolation(
            _Code.VOICE_TRANSCRIPTION_DAILY_LIMIT, params={"limit": limit}
        ) from None
    except usage_repo.AccountNotWritable:
        raise VoiceQuestionViolation(
            _Code.VOICE_QUESTIONS_NOT_ALLOWED, internal_detail="account not writable"
        ) from None
    except usage_repo.UsageUnavailable:
        raise VoiceQuestionViolation(
            _Code.VOICE_TRANSCRIPTION_UNAVAILABLE, internal_detail="counter unavailable"
        ) from None

    try:
        text = transcriber().transcribe(audio, recording.container)
    except TranscriptionFailed as exc:
        _give_back(student_id, day, table=table)
        raise VoiceQuestionViolation(
            _Code.VOICE_TRANSCRIPTION_UNAVAILABLE, internal_detail=exc.reason
        ) from None
    if not text:
        raise VoiceQuestionViolation(_Code.VOICE_RECORDING_SILENT)
    return text


def _give_back(student_id: str, day: str, *, table: Any | None) -> None:
    try:
        usage_repo.give_back(student_id, day, table=table)
    except (usage_repo.UsageUnavailable, usage_repo.AccountNotWritable):
        # The student loses one of the day's transcriptions; nothing else.
        logger.warning(
            "voice transcription count not given back",
            extra={"event": "voice_transcription_count_kept"},
        )
