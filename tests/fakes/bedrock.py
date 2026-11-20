"""Bedrock Runtime on the wire, for testing the Bedrock adapter of 模型调用 (#436, #439).

The adapter is tested on a real botocore client, never on a hand-written one:
CountTokens and error replies through botocore's `Stubber`, the response
stream as event-stream bytes on the wire (`streaming`), decoded by botocore's
own parser, since `Stubber` cannot carry a stream body.
"""

from __future__ import annotations

import base64
import binascii
import json
import struct
from collections.abc import Mapping
from typing import Any

import boto3
from botocore.awsrequest import AWSResponse


def runtime() -> Any:
    return boto3.client(
        "bedrock-runtime",
        region_name="eu-central-2",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )


def _header(name: str, value: str) -> bytes:
    encoded_name, encoded_value = name.encode(), value.encode()
    return (
        struct.pack("!B", len(encoded_name))
        + encoded_name
        + struct.pack("!BH", 7, len(encoded_value))
        + encoded_value
    )


def event_message(event: Mapping[str, Any]) -> bytes:
    """One `chunk` event of InvokeModelWithResponseStream, as it is on the wire."""
    payload = json.dumps(
        {"bytes": base64.b64encode(json.dumps(event).encode()).decode()}
    ).encode()
    headers = (
        _header(":event-type", "chunk")
        + _header(":message-type", "event")
        + _header(":content-type", "application/json")
    )
    prelude = struct.pack("!II", 12 + len(headers) + len(payload) + 4, len(headers))
    prelude += struct.pack("!I", binascii.crc32(prelude) & 0xFFFFFFFF)
    message = prelude + headers + payload
    return message + struct.pack("!I", binascii.crc32(message) & 0xFFFFFFFF)


class Wire:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def stream(self, *_args: Any, **_kwargs: Any):
        yield self._data

    def read(self, *_args: Any, **_kwargs: Any) -> bytes:
        return self._data

    def close(self) -> None:
        return None


def streaming(client: Any, events: list[Mapping[str, Any]], sent: list[bytes]) -> None:
    def send(request: Any, **_kwargs: Any) -> AWSResponse:
        sent.append(request.body)
        return AWSResponse(
            request.url,
            200,
            {
                "x-amzn-RequestId": "req-bdrk-1",
                "content-type": "application/vnd.amazon.eventstream",
            },
            Wire(b"".join(event_message(event) for event in events)),
        )

    client.meta.events.register(
        "before-send.bedrock-runtime.InvokeModelWithResponseStream", send
    )
