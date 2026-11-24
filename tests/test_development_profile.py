"""Which inference profile a development script invokes through (#612)."""

from __future__ import annotations

from typing import Any

import boto3
from botocore.stub import Stubber
import pytest

from stoa.services.model_call import development_profile as profiles

MODEL_ID = "eu.anthropic.claude-sonnet-4-6"
NAME = "stoa-development-eu-anthropic-claude-sonnet-4-6"
ARN = "arn:aws:bedrock:eu-central-2:111122223333:application-inference-profile/dev123"


class _Session:
    def __init__(self, client: Any) -> None:
        self._client = client
        self.asked: list[tuple[str, str]] = []

    def client(self, service: str, *, region_name: str) -> Any:
        self.asked.append((service, region_name))
        return self._client


def _bedrock() -> Any:
    return boto3.client(
        "bedrock",
        region_name="eu-central-2",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )


def _summary(name: str, arn: str, status: str = "ACTIVE") -> dict[str, Any]:
    return {
        "inferenceProfileName": name,
        "inferenceProfileArn": arn,
        "inferenceProfileId": arn.rsplit("/", 1)[1],
        "models": [{"modelArn": "arn:aws:bedrock:eu-central-2::foundation-model/x"}],
        "status": status,
        "type": "APPLICATION",
    }


def test_the_profiles_are_named_after_their_use_and_their_model() -> None:
    """The rule stoa-infra names them by; a name holds letters, digits and hyphens."""
    assert profiles.profile_name(profiles.DEVELOPMENT, MODEL_ID) == NAME
    assert (
        profiles.profile_name(profiles.PRODUCT, MODEL_ID)
        == "stoa-product-eu-anthropic-claude-sonnet-4-6"
    )
    assert (
        profiles.profile_name(profiles.DEVELOPMENT, "eu.anthropic.claude-haiku-4-5-20251001-v1:0")
        == "stoa-development-eu-anthropic-claude-haiku-4-5-20251001-v1-0"
    )


def test_a_script_invokes_through_the_development_profile_of_its_model(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _bedrock()
    session = _Session(client)
    with Stubber(client) as stub:
        stub.add_response(
            "list_inference_profiles",
            {
                "inferenceProfileSummaries": [
                    _summary("stoa-product-eu-anthropic-claude-sonnet-4-6", ARN + "x")
                ],
                "nextToken": "more",
            },
            {"typeEquals": "APPLICATION"},
        )
        stub.add_response(
            "list_inference_profiles",
            {"inferenceProfileSummaries": [_summary(NAME, ARN)]},
            {"typeEquals": "APPLICATION", "nextToken": "more"},
        )

        found = profiles.development_profile(session, region="eu-central-2", model_id=MODEL_ID)

    assert found == ARN
    assert session.asked == [("bedrock", "eu-central-2")]
    captured = capsys.readouterr()
    assert captured.out == ""
    assert NAME in captured.err and "WARNING" not in captured.err


def test_a_model_without_a_development_profile_is_invoked_directly_and_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _bedrock()
    with Stubber(client) as stub:
        stub.add_response(
            "list_inference_profiles",
            {"inferenceProfileSummaries": []},
            {"typeEquals": "APPLICATION"},
        )

        found = profiles.development_profile(
            _Session(client), region="eu-central-2", model_id=MODEL_ID
        )

    assert found == MODEL_ID
    err = capsys.readouterr().err
    assert err.startswith("WARNING") and "does not exist" in err and NAME in err


def test_a_lookup_bedrock_refuses_does_not_stop_the_script(
    capsys: pytest.CaptureFixture[str],
) -> None:
    client = _bedrock()
    with Stubber(client) as stub:
        stub.add_client_error(
            "list_inference_profiles",
            service_error_code="AccessDeniedException",
            http_status_code=403,
        )

        found = profiles.development_profile(
            _Session(client), region="eu-central-2", model_id=MODEL_ID
        )

    assert found == MODEL_ID
    assert "could not be looked up (AccessDeniedException)" in capsys.readouterr().err
