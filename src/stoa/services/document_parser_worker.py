"""Spawn-isolated, resource-bounded document parser boundary."""

from __future__ import annotations

from dataclasses import dataclass
import multiprocessing
import os
import sys
import threading
import time
from typing import Any, Callable

from stoa.config import DOCUMENT_MAX_BYTES


MAX_PARSER_INPUT_BYTES = DOCUMENT_MAX_BYTES
MAX_PARSER_RESULT_CHARACTERS = 200_000
PARSER_CPU_SECONDS = 3
PARSER_ADDRESS_SPACE_BYTES = 1024 * 1024 * 1024
PARSER_WALL_SECONDS = 8.0
_READ_CHUNK_BYTES = 1024 * 1024
_CLOSED_CATEGORIES = {
    "active_content",
    "content_mismatch",
    "document_limit_exceeded",
    "encrypted_document",
    "invalid_document",
    "no_extractable_text",
    "parser_timeout",
    "service_unavailable",
    "unsupported_document",
}


@dataclass(frozen=True, slots=True)
class ParserResult:
    text: str | None = None
    category: str | None = None

    def __post_init__(self) -> None:
        if (self.text is None) == (self.category is None):
            raise ValueError("parser_result_shape")


def parse_document_isolated(
    data: bytes | Any,
    media_type: str,
    *,
    timeout_seconds: float = PARSER_WALL_SECONDS,
) -> ParserResult:
    """Parse one bounded input under spawn, rlimit, IPC, and wall-time fences."""
    raw = _bounded_input(data)
    if raw is None:
        return ParserResult(category="document_limit_exceeded")
    if not isinstance(media_type, str) or not media_type or timeout_seconds <= 0:
        return ParserResult(category="service_unavailable")
    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_worker_main,
        args=(child, raw, media_type),
        name="stoa-document-parser",
        daemon=True,
    )
    try:
        process.start()
    except Exception:
        parent.close()
        child.close()
        return ParserResult(category="service_unavailable")
    child.close()
    return _await_worker_result(
        process,
        parent,
        deadline=time.monotonic() + min(float(timeout_seconds), PARSER_WALL_SECONDS),
    )


def _bounded_input(data: bytes | Any) -> bytes | None:
    if isinstance(data, bytes):
        return data if len(data) <= MAX_PARSER_INPUT_BYTES else None
    output = bytearray()
    try:
        data.seek(0)
        while True:
            chunk = data.read(_READ_CHUNK_BYTES)
            if not chunk:
                return bytes(output)
            if not isinstance(chunk, bytes):
                return None
            if len(output) + len(chunk) > MAX_PARSER_INPUT_BYTES:
                return None
            output.extend(chunk)
    except Exception:
        return None


def _worker_main(connection, raw: bytes, media_type: str) -> None:
    try:
        _silence_worker_output()
        if not _apply_resource_limits():
            _send_result(connection, ParserResult(category="service_unavailable"))
            return
        from stoa.services.document_extraction_service import (
            DocumentExtractionFailure,
            extract_attachment_text,
        )

        try:
            text = extract_attachment_text(raw, media_type)
            if len(text) > MAX_PARSER_RESULT_CHARACTERS:
                result = ParserResult(category="document_limit_exceeded")
            else:
                result = ParserResult(text=text)
        except DocumentExtractionFailure as error:
            category = (
                error.category
                if error.category in _CLOSED_CATEGORIES
                else "invalid_document"
            )
            result = ParserResult(category=category)
        except BaseException:
            result = ParserResult(category="invalid_document")
        _send_result(connection, result)
    except BaseException:
        try:
            _send_result(connection, ParserResult(category="service_unavailable"))
        except BaseException:
            pass
    finally:
        try:
            connection.close()
        except BaseException:
            pass


def _send_result(connection, result: ParserResult) -> None:
    payload = {"text": result.text, "category": result.category}
    connection.send(payload)


def _apply_resource_limits() -> bool:
    try:
        import resource

        resource.setrlimit(
            resource.RLIMIT_CPU,
            (PARSER_CPU_SECONDS, PARSER_CPU_SECONDS),
        )
        try:
            resource.setrlimit(
                resource.RLIMIT_AS,
                (PARSER_ADDRESS_SPACE_BYTES, PARSER_ADDRESS_SPACE_BYTES),
            )
        except (OSError, ValueError):
            if sys.platform != "darwin":
                return False
            _start_darwin_memory_watchdog(resource)
        if hasattr(resource, "RLIMIT_CORE"):
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return True
    except (ImportError, OSError, ValueError):
        return False


def _start_darwin_memory_watchdog(resource_module) -> None:
    """Use the Darwin resident-set counter when RLIMIT_AS is unsupported."""

    def watch() -> None:
        while True:
            usage = resource_module.getrusage(resource_module.RUSAGE_SELF).ru_maxrss
            if usage > PARSER_ADDRESS_SPACE_BYTES:
                os._exit(70)
            time.sleep(0.01)

    threading.Thread(
        target=watch,
        name="stoa-parser-memory-watchdog",
        daemon=True,
    ).start()


def _silence_worker_output() -> None:
    descriptor = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(descriptor, 1)
        os.dup2(descriptor, 2)
    finally:
        os.close(descriptor)


def _await_worker_result(
    process,
    connection,
    *,
    deadline: float,
    monotonic: Callable[[], float] = time.monotonic,
) -> ParserResult:
    result: ParserResult | None = None
    try:
        while monotonic() < deadline:
            remaining = max(0.0, deadline - monotonic())
            if connection.poll(min(0.05, remaining)):
                try:
                    result = _validated_payload(connection.recv())
                except (EOFError, OSError, ValueError):
                    result = ParserResult(category="service_unavailable")
                break
            if not process.is_alive():
                result = ParserResult(category="service_unavailable")
                break
        if result is None:
            result = ParserResult(category="parser_timeout")
    finally:
        try:
            connection.close()
        except Exception:
            pass
        _stop_and_join(process)
    return result


def _validated_payload(payload: Any) -> ParserResult:
    if not isinstance(payload, dict) or set(payload) != {"text", "category"}:
        raise ValueError("parser_payload_shape")
    text = payload["text"]
    category = payload["category"]
    if text is not None:
        if not isinstance(text, str) or len(text) > MAX_PARSER_RESULT_CHARACTERS:
            raise ValueError("parser_payload_text")
        return ParserResult(text=text)
    if category not in _CLOSED_CATEGORIES:
        raise ValueError("parser_payload_category")
    return ParserResult(category=category)


def _stop_and_join(process) -> None:
    try:
        if process.is_alive():
            process.terminate()
        process.join(timeout=1.0)
        if process.is_alive():
            kill = getattr(process, "kill", None)
            if callable(kill):
                kill()
            process.join(timeout=1.0)
    except Exception:
        pass


# Kept private but injectable so tests can deterministically prove timeout cleanup.
_await_worker_result_for_tests = _await_worker_result
