"""The Bedrock adapter of 模型调用 (#436): Runtime CountTokens and InvokeModelWithResponseStream.

This is where the service talks to Bedrock about a model call. One connection
is one botocore client, built for the call with one attempt and reads bounded
by the time the call has left, so nothing waits on a socket past the deadline
or retries behind the caller's back. Errors come back as `ProviderError`, with
Bedrock's code, HTTP status, request id and message.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import json
from typing import Any

from botocore.config import Config
from botocore.exceptions import ClientError

from stoa import aws
from stoa.aws import Kind
from stoa.services.model_call.adapter import MalformedStream, ProviderError, Stream

# Kept back from the time left for the read itself, so a read that times out
# still leaves the caller time to record the failure.
_READ_MARGIN_SECONDS = 5
_CONNECT_TIMEOUT_SECONDS = 5

# The prefixes of the system cross-region inference profiles; the foundation
# model is what follows.
_INFERENCE_PROFILE_PREFIXES = ("eu.", "us.", "global.")


def runtime_config(remaining_seconds: float) -> Config:
    """One attempt, the connection bounded, reads bounded by the time left."""
    return Config(
        connect_timeout=_CONNECT_TIMEOUT_SECONDS,
        read_timeout=max(1, int(remaining_seconds - _READ_MARGIN_SECONDS)),
        retries={"total_max_attempts": 1, "mode": "standard"},
    )


def _provider_error(error: Exception) -> ProviderError:
    """What Bedrock said about a failed call, or what failed on the way there."""
    if isinstance(error, ProviderError):
        return error
    if isinstance(error, ClientError):
        response = error.response if isinstance(error.response, Mapping) else {}
        details = response.get("Error") if isinstance(response.get("Error"), Mapping) else {}
        metadata = (
            response.get("ResponseMetadata")
            if isinstance(response.get("ResponseMetadata"), Mapping)
            else {}
        )
        status = metadata.get("HTTPStatusCode")
        request_id = metadata.get("RequestId")
        return ProviderError(
            str(details.get("Code") or type(error).__name__),
            http_status=status if type(status) is int else None,
            request_id=request_id if isinstance(request_id, str) and request_id else None,
            message=str(details.get("Message") or ""),
        )
    # Not Bedrock's answer (a timeout, a connection that failed): its class
    # only, since its text is not the provider's.
    return ProviderError(type(error).__name__)


def _request_id(response: Mapping[str, Any]) -> str:
    metadata = response.get("ResponseMetadata")
    if isinstance(metadata, Mapping) and isinstance(metadata.get("RequestId"), str):
        return metadata["RequestId"].strip()
    return ""


def _count_model_id(model_id: str) -> str:
    """CountTokens takes the foundation model, not the inference profile it is invoked through."""
    for prefix in _INFERENCE_PROFILE_PREFIXES:
        if model_id.startswith(prefix) and len(model_id) > len(prefix):
            return model_id.removeprefix(prefix)
    return model_id


class BedrockConnection:
    def __init__(self, client: Any) -> None:
        self._client = client

    def count(self, model_id: str, body: Mapping[str, Any]) -> int:
        try:
            response = self._client.count_tokens(
                modelId=_count_model_id(model_id),
                input={"invokeModel": {"body": json.dumps(body)}},
            )
        except Exception as error:
            raise _provider_error(error) from None
        if not isinstance(response, Mapping):
            raise ProviderError("MalformedCountResponse")
        metadata = response.get("ResponseMetadata")
        status = metadata.get("HTTPStatusCode") if isinstance(metadata, Mapping) else None
        request_id = _request_id(response)
        count = response.get("inputTokens")
        if status != 200 or not request_id or type(count) is not int or count < 0:
            raise ProviderError(
                "MalformedCountResponse",
                http_status=status if type(status) is int else None,
                request_id=request_id or None,
            )
        return count

    def stream(self, model_id: str, body: Mapping[str, Any]) -> Stream:
        try:
            response = self._client.invoke_model_with_response_stream(
                modelId=model_id, body=json.dumps(body)
            )
        except Exception as error:
            raise _provider_error(error) from None
        if not isinstance(response, Mapping) or response.get("body") is None:
            raise MalformedStream()
        return Stream(request_id=_request_id(response), events=_events(response["body"]))


def _events(body: Any) -> Iterator[Mapping[str, Any]]:
    """The decoded events of the response stream; a failure while reading is a `ProviderError`."""
    iterator = iter(body)
    while True:
        try:
            event = next(iterator)
        except StopIteration:
            return
        except Exception as error:
            raise _provider_error(error) from None
        chunk = event.get("chunk") if isinstance(event, Mapping) else None
        if not chunk:
            continue
        try:
            payload = json.loads(chunk["bytes"])
        except (KeyError, TypeError, ValueError):
            raise MalformedStream() from None
        if not isinstance(payload, Mapping):
            raise MalformedStream()
        yield payload


class BedrockAdapter:
    """Bedrock Runtime in the API's region; `client`, when given, is used as it is."""

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def connect(self, remaining_seconds: float) -> BedrockConnection:
        client = self._client or aws.client(
            Kind.BEDROCK_RUNTIME, config=runtime_config(remaining_seconds)
        )
        return BedrockConnection(client)
