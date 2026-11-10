"""`stoa.aws`: the one entry point for AWS clients and the one place a test installs one (#358)."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from botocore.config import Config

from stoa import aws
from stoa.aws import Kind
from stoa import config

SRC = Path(__file__).resolve().parents[1] / "src" / "stoa"

# The only files in `src/stoa` that may build a boto3 client, resource or session
# themselves. Everything else names a kind of `stoa.aws.client`.
ALLOWED_DIRECT_BOTO3 = frozenset({
    "aws.py",
    "db/table.py",
    "services/subscription_service.py",
    "security/aws_operator_identity.py",
})

_DIRECT_BOTO3 = re.compile(
    r"\bboto3\s*\.\s*(client|resource|Session|session\s*\.\s*Session)\s*\("
    r"|\bfrom\s+boto3\s+import\s+[^\n]*\b(client|resource|Session)\b"
    r"|\.create_client\s*\("
)


def direct_boto3_callers(sources: dict[str, str]) -> list[str]:
    """The files, relative to `src/stoa`, that build a boto3 client outside the allow list."""
    return sorted(
        path
        for path, text in sources.items()
        if path not in ALLOWED_DIRECT_BOTO3 and _DIRECT_BOTO3.search(text)
    )


def _sources() -> dict[str, str]:
    return {
        path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
        for path in SRC.rglob("*.py")
    }


@pytest.fixture
def credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.delenv("AWS_SESSION_TOKEN", raising=False)
    monkeypatch.delenv("AWS_PROFILE", raising=False)
    aws.install(None)


# ── The gate ──────────────────────────────────────────────────────────────────


def test_no_file_outside_the_allow_list_builds_a_boto3_client() -> None:
    assert direct_boto3_callers(_sources()) == []


def test_the_gate_turns_red_when_a_file_builds_its_own_client() -> None:
    sources = _sources()
    sources["services/notify_service.py"] += '\nses = boto3.client("ses")\n'
    sources["jobs/new_job.py"] = "s = boto3.Session()\n"
    sources["deps.py"] += '\nddb = boto3.resource("dynamodb")\n'
    sources["jobs/aliased.py"] = "from boto3 import client as make\n"
    sources["jobs/botocore_direct.py"] = 'c = get_session().create_client("s3")\n'

    assert direct_boto3_callers(sources) == [
        "deps.py", "jobs/aliased.py", "jobs/botocore_direct.py", "jobs/new_job.py",
        "services/notify_service.py",
    ]


def test_every_allowed_file_exists() -> None:
    assert all((SRC / path).is_file() for path in ALLOWED_DIRECT_BOTO3)


# ── The test installation point ───────────────────────────────────────────────


def test_a_kind_no_test_installed_raises_instead_of_reaching_aws() -> None:
    with pytest.raises(aws.NotInstalled, match="ses"):
        aws.client(Kind.SES)


def test_an_installed_double_is_returned_and_the_request_recorded() -> None:
    ses = object()
    aws.install({Kind.SES: ses})

    assert aws.client(Kind.SES) is ses
    [request] = aws.requests()
    assert request.kind is Kind.SES
    assert request.service == "ses"
    assert request.region == config.settings().aws_region


def test_installs_add_up() -> None:
    s3, ses = object(), object()
    aws.install({Kind.S3: s3})
    aws.install({Kind.SES: ses})

    assert aws.client(Kind.S3) is s3
    assert aws.client(Kind.SES) is ses


def test_a_per_call_config_reaches_the_double_and_the_record() -> None:
    bedrock = object()
    aws.install({Kind.BEDROCK_RUNTIME: bedrock})

    assert aws.client(Kind.BEDROCK_RUNTIME, config=Config(read_timeout=7)) is bedrock
    assert aws.requests()[0].config.read_timeout == 7


def test_a_websocket_client_needs_its_endpoint() -> None:
    aws.install({Kind.WEBSOCKET_MANAGEMENT: object()})
    with pytest.raises(ValueError, match="endpoint_url"):
        aws.client(Kind.WEBSOCKET_MANAGEMENT)

    aws.client(Kind.WEBSOCKET_MANAGEMENT, endpoint_url="https://ws.example/prod")
    assert aws.requests()[-1].endpoint_url == "https://ws.example/prod"


# ── The table: regions and configs, as they were at each call site ────────────


@pytest.mark.parametrize(
    ("kind", "service"),
    [
        (Kind.S3, "s3"),
        (Kind.S3_PRESIGN, "s3"),
        (Kind.SES, "ses"),
        (Kind.SES_DISPATCH_REMINDER, "ses"),
        (Kind.COGNITO, "cognito-idp"),
        (Kind.BEDROCK_RUNTIME, "bedrock-runtime"),
        (Kind.LAMBDA, "lambda"),
        (Kind.LAMBDA_GENERATION, "lambda"),
        (Kind.SQS, "sqs"),
    ],
)
def test_api_region_kinds(kind: Kind, service: str) -> None:
    aws.install({kind: object()})
    aws.client(kind)
    [request] = aws.requests()
    assert (request.service, request.region) == (service, config.settings().aws_region)


def test_bounded_configs_are_kept() -> None:
    reminder = aws.KINDS[Kind.SES_DISPATCH_REMINDER].config
    generation = aws.KINDS[Kind.LAMBDA_GENERATION].config
    for bounded in (reminder, generation):
        assert (bounded.connect_timeout, bounded.read_timeout) == (2, 3)
        assert bounded.retries == {"max_attempts": 1, "mode": "standard"}


# ── Real clients ──────────────────────────────────────────────────────────────


def test_a_real_client_is_built_once_per_kind_and_region(credentials: None) -> None:
    first = aws.client(Kind.SES)
    assert aws.client(Kind.SES) is first
    assert aws.client(Kind.SES_DISPATCH_REMINDER) is not first
    assert aws.client(Kind.SES, region="eu-west-1") is not first
    assert aws.client(Kind.SES, region="eu-west-1").meta.region_name == "eu-west-1"


def test_a_per_call_config_builds_a_fresh_client_that_is_not_kept(credentials: None) -> None:
    one = aws.client(Kind.BEDROCK_RUNTIME, config=Config(read_timeout=9))
    two = aws.client(Kind.BEDROCK_RUNTIME, config=Config(read_timeout=9))

    assert one is not two
    assert one.meta.config.read_timeout == 9
    assert aws.client(Kind.BEDROCK_RUNTIME) is aws.client(Kind.BEDROCK_RUNTIME)


def test_building_a_real_client_leaves_the_kinds_config_as_written(credentials: None) -> None:
    aws.client(Kind.SES_DISPATCH_REMINDER)
    aws.client(Kind.LAMBDA_GENERATION)

    for kind in (Kind.SES_DISPATCH_REMINDER, Kind.LAMBDA_GENERATION):
        assert aws.KINDS[kind].config.retries == {"max_attempts": 1, "mode": "standard"}


def test_a_presigned_url_names_the_buckets_regional_virtual_host(credentials: None) -> None:
    region = config.settings().aws_region
    url = aws.client(Kind.S3_PRESIGN).generate_presigned_url(
        "put_object", Params={"Bucket": "stoa-images", "Key": "a/b.png"}, ExpiresIn=60
    )

    parts = urlsplit(url)
    assert parts.hostname == f"stoa-images.s3.{region}.amazonaws.com"
    assert "X-Amz-Algorithm=AWS4-HMAC-SHA256" in parts.query


def test_the_moderation_client_keeps_its_region_timeouts_and_retries(credentials: None) -> None:
    moderation = aws.client(Kind.REKOGNITION_MODERATION)

    assert moderation.meta.region_name == config.settings().image_moderation_region
    built = moderation.meta.config
    assert (built.connect_timeout, built.read_timeout) == (2, 5)
    assert built.retries["mode"] == "standard"
    assert built.retries["total_max_attempts"] == 2


def test_the_websocket_client_talks_to_its_endpoint(credentials: None) -> None:
    management = aws.client(
        Kind.WEBSOCKET_MANAGEMENT, endpoint_url="https://abc.execute-api.eu-central-2.amazonaws.com/prod"
    )
    assert management.meta.endpoint_url == "https://abc.execute-api.eu-central-2.amazonaws.com/prod"
