"""What an operator operation answers, or why it declines (#383, #384)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Outcome:
    """What an operation answers, and what its audit row says it touched."""

    result: dict[str, object]
    target_type: str
    target_id: str
    evidence: str = ""


class OperatorCallRefused(Exception):
    """A call that is declined. The message goes to the agent as is, so it names
    account numbers and states at most - never an address, a token or an input."""

    def __init__(
        self, code: str, message: str, *, target_type: str = "", target_id: str = ""
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.target_type = target_type
        self.target_id = target_id
