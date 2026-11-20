"""What a 模型调用 adapter is: the one seam between the call and the provider (#436).

An adapter knows how to reach the provider and nothing about what is asked of
it. The call builds both request bodies (the one sent and the one counted) and
reads the events that come back; the adapter only carries them:

- `connect(remaining_seconds)` opens one connection for one call, its reads
  bounded by the time left before the call's deadline;
- `Connection.count(model_id, body)` asks the provider how many input
  tokens `body` costs;
- `Connection.stream(model_id, body)` sends `body` and hands back the
  provider's request id and its stream of decoded events.

Whatever the provider refuses, or fails to answer, is raised as
`ProviderError`, with what the provider said about it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol


class ProviderError(Exception):
    """The provider refused the request or failed to answer it.

    `code` is the provider's error code (`ValidationException`,
    `ThrottlingException`, ...) or, for a failure on the way there, the
    exception's class; `http_status` and `request_id` are the provider's when
    it answered at all; `message` is its error text, kept private.
    """

    def __init__(
        self,
        code: str,
        *,
        http_status: int | None = None,
        request_id: str | None = None,
        message: str = "",
    ) -> None:
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.request_id = request_id
        self.message = message


class MalformedStream(Exception):
    """An event of the stream could not be read as one."""


@dataclass(frozen=True, slots=True)
class Stream:
    """A sent request: the provider's id for it and its decoded events, in order."""

    request_id: str
    events: Iterable[Mapping[str, Any]]


class Connection(Protocol):
    def count(self, model_id: str, body: Mapping[str, Any]) -> int: ...

    def stream(self, model_id: str, body: Mapping[str, Any]) -> Stream: ...


class Adapter(Protocol):
    def connect(self, remaining_seconds: float) -> Connection: ...
