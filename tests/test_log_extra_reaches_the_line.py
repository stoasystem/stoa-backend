"""What a log call attaches as `extra` must be in the line CloudWatch keeps (#503).

`stoa-api` logs in Lambda's Text format. The Python runtime puts one handler on
the root logger whose formatter writes the level, the time, the request id and
`%(message)s` - nothing else - so a fact passed as `extra` was dropped and a
refused voice transcription reached CloudWatch as "voice transcription refused"
with no error code and no request id.

These tests format records the way that handler does and read the line, not the
record: a record attribute is exactly what was lost in production.
"""

from __future__ import annotations

import ast
import importlib
import io
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from botocore.exceptions import ClientError

from fakes.converse import FakeConverse, client_error
from stoa import aws
from stoa.security import public_auth_errors
from stoa.services import transcription, voice_transcription
from stoa.services.voice_audio import Container

SRC = Path(__file__).resolve().parents[1] / "src"

# The Lambda Python runtime's Text formatter (awslambdaric `bootstrap._setup_logging`),
# the one that wrote the production line quoted in #503:
#   [WARNING]	2026-11-17T17:54:04.269Z	e35e7101-…	public_auth_provider_failure
LAMBDA_TEXT_FORMAT = "[%(levelname)s]\t%(asctime)s.%(msecs)03dZ\t%(aws_request_id)s\t%(message)s\n"
LAMBDA_TEXT_DATEFMT = "%Y-%m-%dT%H:%M:%S"
_LOG_METHODS = frozenset({"debug", "info", "warning", "warn", "error", "exception", "critical", "log"})


class _LambdaRequestId(logging.Filter):
    """The runtime's own filter stamps the invocation's request id on every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.aws_request_id = "e35e7101-0000-0000-0000-000000000000"
        return True


@pytest.fixture
def lambda_lines() -> Iterator[io.StringIO]:
    """What the Lambda runtime's handler writes, for every `stoa` logger."""
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter(LAMBDA_TEXT_FORMAT, LAMBDA_TEXT_DATEFMT))
    handler.addFilter(_LambdaRequestId())
    stoa_logger = logging.getLogger("stoa")
    stoa_logger.addHandler(handler)
    previous = stoa_logger.level
    stoa_logger.setLevel(logging.INFO)
    try:
        yield stream
    finally:
        stoa_logger.removeHandler(handler)
        stoa_logger.setLevel(previous)


def _log_facts():
    # Imported here so the line tests above fail on what they read, not on import.
    return importlib.import_module("stoa.log_facts")


def _line(stream: io.StringIO, marker: str) -> str:
    [line] = [line for line in stream.getvalue().splitlines() if marker in line]
    return line


def test_a_refused_voice_transcription_line_carries_the_code_and_request_id(
    lambda_lines: io.StringIO,
) -> None:
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: FakeConverse(client_error("ValidationException"))})

    with pytest.raises(transcription.TranscriptionFailed):
        transcription.VoxtralTranscriber(model_id="mistral.voxtral-small-2507").transcribe(
            b"\x1a\x45\xdf\xa3", Container.WAV
        )

    line = _line(lambda_lines, "voice transcription refused")
    # The phrase stoa-infra's alarm matches stays first, untouched.
    assert line.split("\t")[3].startswith("voice transcription refused ")
    assert "event=voice_transcription_refused" in line
    assert "provider_error_code=ValidationException" in line
    assert "provider_request_id=ValidationException-request" in line
    assert "model_id=mistral.voxtral-small-2507" in line
    assert "audio_format=wav" in line


def test_a_failed_voice_transcription_line_carries_the_code(lambda_lines: io.StringIO) -> None:
    aws.install({aws.Kind.VOICE_TRANSCRIPTION: FakeConverse(client_error("ThrottlingException"))})

    with pytest.raises(transcription.TranscriptionFailed):
        transcription.VoxtralTranscriber(model_id="m").transcribe(b"\x00", Container.WAV)

    line = _line(lambda_lines, "voice transcription failed")
    assert "event=voice_transcription_failed" in line
    assert "provider_error_code=ThrottlingException" in line
    assert "provider_request_id=ThrottlingException-request" in line


def test_a_count_not_given_back_is_named_in_the_line(
    lambda_lines: io.StringIO, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable(*_args: object, **_kwargs: object) -> None:
        raise voice_transcription.usage_repo.UsageUnavailable()

    monkeypatch.setattr(voice_transcription.usage_repo, "give_back", unavailable)
    voice_transcription._give_back("student-1", "2026-11-18", table=None)

    line = _line(lambda_lines, "voice transcription count not given back")
    assert "event=voice_transcription_count_kept" in line


def test_a_public_auth_failure_line_carries_its_telemetry(lambda_lines: io.StringIO) -> None:
    error = ClientError(
        {"Error": {"Code": "SomethingNew", "Message": "secret@example.test"}},
        "InitiateAuth",
    )

    failure = public_auth_errors.normalize_cognito_failure(
        public_auth_errors.PublicAuthOperation.REFRESH, error, "corr-503"
    )

    line = _line(lambda_lines, "public_auth_provider_failure")
    assert f"public_auth.operation={failure.operation.value}" in line
    assert "public_auth.correlation_id=corr-503" in line
    assert "public_auth.category=provider_unavailable" in line
    assert f"public_auth.provider_code_digest={failure.provider_code_digest}" in line
    # Only the digest of the provider's code, never the code or its message.
    assert "SomethingNew" not in line
    assert "secret@example.test" not in line


def test_a_value_cannot_forge_a_field_or_a_line(lambda_lines: io.StringIO) -> None:
    logger = _log_facts().get_logger("stoa.test_log_extra")

    logger.warning(
        "forge attempt",
        extra={"provider_request_id": "abc event=forged\n[ERROR]\tfake", "count": 3, "empty": None},
    )

    line = _line(lambda_lines, "forge attempt")
    assert line.endswith(
        "forge attempt provider_request_id=abc_event_forged__ERROR__fake count=3 empty=-"
    )
    assert line.count("=") == 3


def test_a_long_value_is_cut() -> None:
    record = logging.LogRecord("stoa.x", logging.INFO, __file__, 1, "m", None, None)
    message, _ = _log_facts().FactLogger(logging.getLogger("stoa.x")).process(
        record.msg, {"extra": {"model_id": "x" * 500}}
    )
    assert message == "m model_id=" + "x" * 96


def _calls_with_extra(path: Path) -> Iterator[tuple[str, int]]:
    """(logger variable, line) for every `<name>.<log method>(..., extra=...)`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _LOG_METHODS
            and isinstance(node.func.value, ast.Name)
            and any(keyword.arg == "extra" for keyword in node.keywords)
        ):
            yield node.func.value.id, node.lineno


def test_every_log_call_with_extra_writes_it_into_the_line() -> None:
    """#503: no `extra=` the Lambda Text line would drop.

    A log call that attaches `extra` must be made on a `log_facts` logger, which
    writes the facts into the message itself.
    """
    fact_logger = _log_facts().FactLogger
    found: list[str] = []
    dropped: list[str] = []
    for path in sorted((SRC / "stoa").rglob("*.py")):
        calls = list(_calls_with_extra(path))
        if not calls:
            continue
        module_name = ".".join(path.relative_to(SRC).with_suffix("").parts)
        module_name = module_name.removesuffix(".__init__")
        module = importlib.import_module(module_name)
        for variable, line in calls:
            where = f"{module_name}:{line} ({variable})"
            found.append(where)
            if not isinstance(getattr(module, variable, None), fact_logger):
                dropped.append(where)

    # The scan sees the call sites #503 names; an empty scan proves nothing.
    assert any(where.startswith("stoa.services.transcription:") for where in found)
    assert any(where.startswith("stoa.security.public_auth_errors:") for where in found)
    assert dropped == []
