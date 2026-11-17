"""The voice transcription's Bedrock runtime double (#477).

Transcription is its own Bedrock call (Converse, through its own
`aws.Kind.VOICE_TRANSCRIPTION` client), not a model call: tests install
`FakeConverse` with `stoa.aws.install`. The Ask answer's model is faked at the
model-call seam instead (`fakes.model`, #436).
"""

from __future__ import annotations

from typing import Any

from botocore.exceptions import ClientError


class FakeConverse:
    """The voice transcription's Bedrock runtime, as boto3 hands it out (#477).

    `converse` records every request it is sent, whole, and answers with the next
    of `outcomes`: a string is the transcription, an exception is raised from the
    call. With none left it answers `transcript`.
    """

    def __init__(self, *outcomes: Any, transcript: str = "Wie rechne ich 3 mal 4?") -> None:
        self.outcomes: list[Any] = list(outcomes)
        self.transcript = transcript
        self.requests: list[dict[str, Any]] = []

    def converse(self, **request: Any) -> dict[str, Any]:
        self.requests.append(request)
        outcome = self.outcomes.pop(0) if self.outcomes else self.transcript
        if isinstance(outcome, BaseException):
            raise outcome
        return {
            "output": {"message": {"role": "assistant", "content": [{"text": outcome}]}},
            "stopReason": "end_turn",
            "usage": {"inputTokens": 400, "outputTokens": 12, "totalTokens": 412},
            "ResponseMetadata": {"RequestId": f"converse-{len(self.requests)}"},
        }


def client_error(code: str, message: str = "", operation: str = "Converse") -> ClientError:
    """A provider error as botocore raises it."""
    return ClientError(
        {
            "Error": {"Code": code, "Message": message},
            "ResponseMetadata": {"HTTPStatusCode": 400, "RequestId": f"{code}-request"},
        },
        operation,
    )
