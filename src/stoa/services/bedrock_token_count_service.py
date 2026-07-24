"""Authoritative Bedrock input-token counting for governed AI admission."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Mapping, Protocol

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.httpsession import URLLib3Session

from stoa.models.allowance import MAX_EXACT_COUNT


MANTLE_ACTION = "bedrock-mantle:CountTokens"
RUNTIME_ACTION = "bedrock:CountTokens"
_MANTLE_PATH = "/anthropic/v1/messages/count_tokens"
_CRIS_PREFIXES = ("eu.", "us.", "global.")
_MANTLE_INPUT_FIELDS = frozenset(
    {
        "messages",
        "system",
        "tools",
        "tool_choice",
        "thinking",
    }
)
_INVOKE_ONLY_FIELDS = frozenset(
    {
        "anthropic_version",
        "max_tokens",
        "temperature",
        "top_k",
        "top_p",
        "stop_sequences",
    }
)


class ProviderTokenCountUnavailable(Exception):
    """Stable fail-closed error for unavailable authoritative counting."""

    category = "provider_token_count_unavailable"

    def __init__(self) -> None:
        super().__init__(self.category)


class MantleCountTokensClient(Protocol):
    """Least-capability dependency for the count-only Mantle endpoint."""

    def count_tokens(
        self,
        *,
        region: str,
        model_id: str,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class TokenCountResult:
    """Redaction-safe authoritative count response."""

    input_tokens: int
    action: str
    request_id: str


def _exact_nonnegative_int(value: object) -> int:
    if type(value) is not int or value < 0 or value > MAX_EXACT_COUNT:
        raise ProviderTokenCountUnavailable()
    return value


def foundation_model_id_for_profile(inference_profile_id: str) -> str:
    """Resolve the model name accepted by Mantle from a system CRIS profile ID."""
    for prefix in _CRIS_PREFIXES:
        if inference_profile_id.startswith(prefix):
            model_id = inference_profile_id.removeprefix(prefix)
            if model_id:
                return model_id
    raise ProviderTokenCountUnavailable()


def _uses_mantle(inference_profile_id: str | None) -> bool:
    if inference_profile_id is None:
        return False
    return inference_profile_id.startswith(_CRIS_PREFIXES)


def _parse_invoke_body(request_body: str) -> dict[str, object]:
    try:
        parsed = json.loads(request_body)
    except (TypeError, json.JSONDecodeError):
        raise ProviderTokenCountUnavailable() from None
    if not isinstance(parsed, dict):
        raise ProviderTokenCountUnavailable()
    if not isinstance(parsed.get("messages"), list):
        raise ProviderTokenCountUnavailable()
    return parsed


def _mantle_payload(request_body: str, *, model_id: str) -> dict[str, object]:
    parsed = _parse_invoke_body(request_body)
    unsupported = set(parsed).difference(_MANTLE_INPUT_FIELDS | _INVOKE_ONLY_FIELDS)
    if unsupported:
        raise ProviderTokenCountUnavailable()
    payload = {
        key: value
        for key, value in parsed.items()
        if key in _MANTLE_INPUT_FIELDS
    }
    payload["model"] = model_id
    return payload


class SigV4MantleCountTokensClient:
    """SigV4 count-only client for CRIS-only Anthropic models."""

    def __init__(self, *, session: object | None = None, http_session: object | None = None):
        self._session = session
        self._http_session = http_session

    def count_tokens(
        self,
        *,
        region: str,
        model_id: str,
        payload: Mapping[str, object],
    ) -> Mapping[str, object]:
        session = self._session or boto3.Session()
        get_credentials = getattr(session, "get_credentials", None)
        if not callable(get_credentials):
            raise ProviderTokenCountUnavailable()
        credentials = get_credentials()
        if credentials is None:
            raise ProviderTokenCountUnavailable()
        get_frozen = getattr(credentials, "get_frozen_credentials", None)
        if callable(get_frozen):
            credentials = get_frozen()

        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
        url = f"https://bedrock-mantle.{region}.api.aws{_MANTLE_PATH}"
        request = AWSRequest(
            method="POST",
            url=url,
            data=body,
            headers={
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )
        SigV4Auth(credentials, "bedrock-mantle", region).add_auth(request)
        prepared = request.prepare()
        transport = self._http_session or URLLib3Session()
        send = getattr(transport, "send", None)
        if not callable(send):
            raise ProviderTokenCountUnavailable()
        response = send(prepared)
        status_code = getattr(response, "status_code", None)
        content = getattr(response, "content", None)
        headers = getattr(response, "headers", {})
        if type(status_code) is not int or status_code != 200 or not isinstance(content, bytes):
            raise ProviderTokenCountUnavailable()
        try:
            parsed = json.loads(content)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ProviderTokenCountUnavailable() from None
        if not isinstance(parsed, dict):
            raise ProviderTokenCountUnavailable()
        request_id = ""
        if isinstance(headers, Mapping):
            raw_request_id = headers.get("x-amzn-requestid") or headers.get("x-amz-request-id")
            if isinstance(raw_request_id, str):
                request_id = raw_request_id.strip()
        return {
            "input_tokens": parsed.get("input_tokens"),
            "request_id": request_id,
            "http_status": status_code,
        }


def count_input_tokens_with_evidence(
    request_body: str,
    *,
    model_id: str,
    inference_profile_id: str | None,
    region: str,
    mantle_client: MantleCountTokensClient | None = None,
    runtime_client: object | None = None,
) -> TokenCountResult:
    """Count the exact InvokeModel request without generation or local estimation."""
    if not model_id or not region:
        raise ProviderTokenCountUnavailable()
    try:
        if _uses_mantle(inference_profile_id):
            if inference_profile_id is None:
                raise ProviderTokenCountUnavailable()
            if foundation_model_id_for_profile(inference_profile_id) != model_id:
                raise ProviderTokenCountUnavailable()
            selected_mantle_client = mantle_client or SigV4MantleCountTokensClient()
            response = selected_mantle_client.count_tokens(
                region=region,
                model_id=model_id,
                payload=_mantle_payload(request_body, model_id=model_id),
            )
            if not isinstance(response, Mapping):
                raise ProviderTokenCountUnavailable()
            if response.get("http_status") != 200:
                raise ProviderTokenCountUnavailable()
            count = _exact_nonnegative_int(response.get("input_tokens"))
            request_id = response.get("request_id")
            if not isinstance(request_id, str) or not request_id.strip():
                raise ProviderTokenCountUnavailable()
            return TokenCountResult(count, MANTLE_ACTION, request_id.strip())

        _parse_invoke_body(request_body)
        selected_runtime_client = runtime_client or boto3.client(
            "bedrock-runtime",
            region_name=region,
        )
        count_tokens = getattr(selected_runtime_client, "count_tokens", None)
        if not callable(count_tokens):
            raise ProviderTokenCountUnavailable()
        response = count_tokens(
            modelId=model_id,
            input={"invokeModel": {"body": request_body}},
        )
        if not isinstance(response, Mapping):
            raise ProviderTokenCountUnavailable()
        count = _exact_nonnegative_int(response.get("inputTokens"))
        metadata = response.get("ResponseMetadata")
        request_id = ""
        if isinstance(metadata, Mapping):
            raw_request_id = metadata.get("RequestId")
            if isinstance(raw_request_id, str):
                request_id = raw_request_id.strip()
        return TokenCountResult(count, RUNTIME_ACTION, request_id)
    except ProviderTokenCountUnavailable:
        raise
    except Exception:
        raise ProviderTokenCountUnavailable() from None


def count_input_tokens(
    request_body: str,
    *,
    model_id: str,
    inference_profile_id: str | None,
    region: str,
    mantle_client: MantleCountTokensClient | None = None,
    runtime_client: object | None = None,
) -> int:
    """Return only the exact provider count used by allowance admission."""
    return count_input_tokens_with_evidence(
        request_body,
        model_id=model_id,
        inference_profile_id=inference_profile_id,
        region=region,
        mantle_client=mantle_client,
        runtime_client=runtime_client,
    ).input_tokens


__all__ = [
    "MANTLE_ACTION",
    "RUNTIME_ACTION",
    "ProviderTokenCountUnavailable",
    "SigV4MantleCountTokensClient",
    "TokenCountResult",
    "count_input_tokens",
    "count_input_tokens_with_evidence",
    "foundation_model_id_for_profile",
]
