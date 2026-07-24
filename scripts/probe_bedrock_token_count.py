#!/usr/bin/env python3
"""Capture or verify a redacted exact-model Bedrock CountTokens preflight."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Mapping

import boto3

from stoa.config import settings
from stoa.services.bedrock_token_count_service import (
    MANTLE_ACTION,
    MantleCountTokensClient,
    ProviderTokenCountUnavailable,
    count_input_tokens_with_evidence,
    foundation_model_id_for_profile,
)


_SCHEMA_VERSION = 1
_SYNTHETIC_INPUT = "Synthetic STOA Bedrock token-count preflight"
_ROOT = Path(__file__).resolve().parents[1]


class PreflightVerificationError(Exception):
    """Static public reason for invalid or stale preflight evidence."""


def _digest(value: str, *, domain: str) -> str:
    return hashlib.sha256(f"stoa:{domain}:v1:{value}".encode()).hexdigest()


def _git_source_sha() -> str:
    completed = subprocess.run(
        [
            "git",
            "log",
            "-1",
            "--format=%H",
            "--",
            "src/stoa/services/bedrock_token_count_service.py",
            "src/stoa/services/ai_service.py",
            "scripts/probe_bedrock_token_count.py",
        ],
        cwd=_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    source_sha = completed.stdout.strip()
    if len(source_sha) != 40 or any(character not in "0123456789abcdef" for character in source_sha):
        raise PreflightVerificationError("source_sha_unavailable")
    return source_sha


def _configuration_values() -> tuple[str, str, str, str]:
    inference_profile_id = settings.bedrock_model_id.strip()
    model_id = foundation_model_id_for_profile(inference_profile_id)
    region = settings.aws_region.strip()
    environment = settings.environment.strip()
    if not region or not environment:
        raise PreflightVerificationError("configuration_unavailable")
    return environment, region, model_id, inference_profile_id


def _environment_digest(environment: str, region: str) -> str:
    return _digest(f"{environment}:{region}", domain="bedrock-preflight-environment")


def _synthetic_body() -> str:
    return json.dumps(
        {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1,
            "temperature": 0,
            "messages": [{"role": "user", "content": _SYNTHETIC_INPUT}],
        },
        separators=(",", ":"),
    )


def _identity_digest(identity: Mapping[str, object]) -> str:
    account = identity.get("Account")
    arn = identity.get("Arn")
    user_id = identity.get("UserId")
    metadata = identity.get("ResponseMetadata")
    if (
        not isinstance(account, str)
        or not account
        or not isinstance(arn, str)
        or not arn
        or not isinstance(user_id, str)
        or not user_id
        or not isinstance(metadata, Mapping)
        or metadata.get("HTTPStatusCode") != 200
    ):
        raise PreflightVerificationError("identity_unavailable")
    return _digest(f"{account}:{arn}:{user_id}", domain="bedrock-preflight-identity")


def capture_preflight(
    results: Path,
    *,
    sts_client: object | None = None,
    mantle_client: MantleCountTokensClient | None = None,
    fixture: bool = False,
    captured_at: datetime | None = None,
) -> dict[str, object]:
    """Run only identity and CountTokens checks, then write redacted evidence."""
    environment, region, model_id, inference_profile_id = _configuration_values()
    if not fixture and (sts_client is not None or mantle_client is not None):
        raise PreflightVerificationError("mock_dependency_rejected")
    sts = sts_client or boto3.client("sts", region_name=region)
    get_caller_identity = getattr(sts, "get_caller_identity", None)
    if not callable(get_caller_identity):
        raise PreflightVerificationError("identity_unavailable")
    try:
        identity = get_caller_identity()
        if not isinstance(identity, Mapping):
            raise PreflightVerificationError("identity_unavailable")
        count_result = count_input_tokens_with_evidence(
            _synthetic_body(),
            model_id=model_id,
            inference_profile_id=inference_profile_id,
            region=region,
            mantle_client=mantle_client,
        )
    except (ProviderTokenCountUnavailable, PreflightVerificationError):
        raise
    except Exception:
        raise PreflightVerificationError("provider_token_count_unavailable") from None
    if count_result.action != MANTLE_ACTION:
        raise PreflightVerificationError("endpoint_mismatch")

    captured = captured_at or datetime.now(timezone.utc)
    if captured.tzinfo is None:
        raise PreflightVerificationError("captured_at_invalid")
    receipt: dict[str, object] = {
        "schemaVersion": _SCHEMA_VERSION,
        "status": "fixture_only" if fixture else "passing",
        "mocked": fixture,
        "sourceSha": _git_source_sha(),
        "environmentDigest": _environment_digest(environment, region),
        "modelDigest": _digest(model_id, domain="bedrock-preflight-model"),
        "inferenceProfileDigest": _digest(
            inference_profile_id,
            domain="bedrock-preflight-profile",
        ),
        "identityDigest": _identity_digest(identity),
        "action": MANTLE_ACTION,
        "syntheticInputTokens": count_result.input_tokens,
        "responseShape": "valid_exact_integer",
        "correlationDigest": _digest(
            count_result.request_id,
            domain="bedrock-preflight-correlation",
        ),
        "capturedAt": captured.astimezone(timezone.utc).isoformat(),
    }
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    for private_value in (
        _SYNTHETIC_INPUT,
        model_id,
        inference_profile_id,
        str(identity.get("Account", "")),
        str(identity.get("Arn", "")),
        str(identity.get("UserId", "")),
        count_result.request_id,
    ):
        if private_value and private_value in rendered:
            raise PreflightVerificationError("redaction_failed")
    results.parent.mkdir(parents=True, exist_ok=True)
    results.write_text(rendered)
    return receipt


def _exact_count(value: object) -> int:
    if type(value) is not int or value < 0:
        raise PreflightVerificationError("malformed_count")
    return value


def _required_digest(receipt: Mapping[str, object], field: str) -> str:
    value = receipt.get(field)
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PreflightVerificationError(f"malformed_{field}")
    return value


def verify_preflight(results: Path) -> dict[str, object]:
    """Verify the receipt is passing, non-mocked, current, and redacted."""
    try:
        raw = results.read_text()
        receipt = json.loads(raw)
    except (OSError, json.JSONDecodeError):
        raise PreflightVerificationError("receipt_unavailable") from None
    if not isinstance(receipt, dict):
        raise PreflightVerificationError("receipt_malformed")
    if receipt.get("schemaVersion") != _SCHEMA_VERSION:
        raise PreflightVerificationError("schema_mismatch")
    if receipt.get("status") != "passing" or receipt.get("mocked") is not False:
        raise PreflightVerificationError("nonpassing_or_mocked")
    if receipt.get("sourceSha") != _git_source_sha():
        raise PreflightVerificationError("source_drift")

    environment, region, model_id, inference_profile_id = _configuration_values()
    expected = {
        "environmentDigest": _environment_digest(environment, region),
        "modelDigest": _digest(model_id, domain="bedrock-preflight-model"),
        "inferenceProfileDigest": _digest(
            inference_profile_id,
            domain="bedrock-preflight-profile",
        ),
    }
    for field, expected_value in expected.items():
        if _required_digest(receipt, field) != expected_value:
            raise PreflightVerificationError("configuration_drift")
    _required_digest(receipt, "identityDigest")
    _required_digest(receipt, "correlationDigest")
    _exact_count(receipt.get("syntheticInputTokens"))
    if receipt.get("action") != MANTLE_ACTION:
        raise PreflightVerificationError("action_mismatch")
    if receipt.get("responseShape") != "valid_exact_integer":
        raise PreflightVerificationError("response_shape_mismatch")
    forbidden = (
        _SYNTHETIC_INPUT,
        model_id,
        inference_profile_id,
        "aws_access_key_id",
        "aws_secret_access_key",
        "aws_session_token",
    )
    if any(value.lower() in raw.lower() for value in forbidden):
        raise PreflightVerificationError("redaction_failed")
    return receipt


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("capture", "verify"):
        subparser = subparsers.add_parser(command)
        subparser.add_argument("--results", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        if args.command == "capture":
            capture_preflight(args.results)
        else:
            verify_preflight(args.results)
    except (ProviderTokenCountUnavailable, PreflightVerificationError) as error:
        print(f"FAIL: {error}")
        return 1
    print(f"PASS: {args.command} Bedrock CountTokens preflight")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
