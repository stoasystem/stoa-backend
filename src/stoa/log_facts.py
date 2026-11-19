"""Facts a log call attaches as `extra`, written into the line itself (#503).

`stoa-api` logs in Lambda's Text format: the Python runtime's handler on the
root logger writes the level, the time, the request id and the message, and
nothing a call attached as `extra`. A refused voice transcription reached
CloudWatch as "voice transcription refused" with no error code and no request id.

A module whose log calls attach `extra` takes its logger from `get_logger`. The
call stays as it was - `logger.warning("voice transcription %s", "refused",
extra={...})` - and the line becomes the message followed by every fact as
`key=value`, in the order given; a nested mapping becomes `outer.key=value`. The
facts stay on the record as well. This works under any handler and formatter,
so it does not depend on the runtime's. `tests/test_log_extra_reaches_the_line.py`
holds every `extra=` in `src/stoa` to a logger made here.

Every key and value is reduced to the characters `emit_private_event` allows
(`stoa.security.private_telemetry`) and cut to 96, so a value cannot forge
another field or start another line. That is the only safety this adds: a fact
is an event name, a provider's error code, an id or a count. Nothing a student
typed and no provider message goes into `extra`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator, Mapping, MutableMapping
from typing import Any

_UNSAFE = re.compile(r"[^A-Za-z0-9._:-]")
_LIMIT = 96


def _token(value: Any, *, fallback: str) -> str:
    return _UNSAFE.sub("_", "" if value is None else str(value))[:_LIMIT] or fallback


def _facts(extra: Mapping[str, Any], prefix: str = "") -> Iterator[str]:
    for key, value in extra.items():
        name = prefix + _token(key, fallback="_")
        if isinstance(value, Mapping):
            yield from _facts(value, prefix=f"{name}.")
        else:
            yield f"{name}={_token(value, fallback='-')}"


class FactLogger(logging.LoggerAdapter):
    """A logger whose `extra` reaches the formatted line as `key=value`."""

    def process(self, msg: Any, kwargs: MutableMapping[str, Any]) -> tuple[Any, MutableMapping[str, Any]]:
        extra = kwargs.get("extra")
        if extra:
            # The facts hold no `%`, so the message's own `%s` arguments still apply.
            msg = f"{msg} {' '.join(_facts(extra))}"
        return msg, kwargs


def get_logger(name: str) -> FactLogger:
    return FactLogger(logging.getLogger(name))
