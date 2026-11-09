"""AWS clients: the one place one is built, and the one place a test puts its own (#358).

Every client the service uses is one of a closed set of kinds (`Kind`). The table
`KINDS` says, for each, which service it talks to, in which region and with which
botocore `Config`; a call site names the kind and nothing else, so the region and the
timeouts of, say, the moderation Rekognition are written down once, here.

- `client(kind)`: the client of that kind. A real one is built once per process for
  each kind, region and endpoint, from one boto3 `Session` under a lock, and reused:
  a warm request does not build an SES, S3 or Cognito client again.
- `client(kind, config=...)`: a client with a per-call `Config` on top of the kind's
  own (the Bedrock call whose timeout is the request's remaining time). It is built
  for that call and not kept.
- `client(kind, region=...)` / `client(kind, endpoint_url=...)`: the few callers whose
  region or endpoint is only known at the call (token counting in the model's region,
  the WebSocket management API at the connection's endpoint).
- `session()`: the shared boto3 `Session`, for the one caller that signs a request
  itself rather than through a client (`bedrock_token_count_service`).
- `install({kind: double})`: the one place a test puts a double. While anything was
  installed, `client` returns the double for its kind and raises `NotInstalled` for any
  other kind - a test never reaches a real client by accident. `requests()` lists what
  was asked for, so a test can check the region, endpoint and `Config` a call site
  used. `install(None)` goes back to real clients.

DynamoDB is not here: the table gateway (`stoa.db.table`) builds its own. Nor are the
operator sessions of `security/aws_operator_identity.py` and the frozen
`subscription_service.py`; `tests/test_aws_client_entry.py` holds the list of the
files allowed to call boto3 directly.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import boto3
from botocore.config import Config

from stoa import config as configuration
from stoa.config import Settings


class Kind(StrEnum):
    S3 = "s3"
    S3_PRESIGN = "s3-presign"
    SES = "ses"
    # Notification emails carry `List-Unsubscribe` headers, which only SESv2
    # `SendEmail` can set (#363); one-off emails stay on SES.
    SES_NOTIFICATION = "ses-notification"
    SES_DISPATCH_REMINDER = "ses-dispatch-reminder"
    COGNITO = "cognito-idp"
    BEDROCK_RUNTIME = "bedrock-runtime"
    LAMBDA = "lambda"
    LAMBDA_GENERATION = "lambda-generation"
    REKOGNITION_MODERATION = "rekognition-moderation"
    SQS = "sqs"
    WEBSOCKET_MANAGEMENT = "apigatewaymanagementapi"


@dataclass(frozen=True)
class Spec:
    service: str
    region: Callable[[Settings], str]
    config: Config | None = None
    needs_endpoint: bool = False


def _api_region(settings: Settings) -> str:
    return settings.aws_region


def _moderation_region(settings: Settings) -> str:
    return settings.image_moderation_region


# Left to its defaults botocore signs for the global `s3.amazonaws.com` host, which
# redirects a request for a Zurich bucket, and a browser does not follow a redirected
# cross-origin PUT. Virtual-hosted addressing in the configured region signs for the
# bucket's regional host.
PRESIGN_CONFIG = Config(signature_version="s3v4", s3={"addressing_style": "virtual"})

# Bounded well inside the request's 29 seconds: the first offer is sent from the
# student's own request, and a slow SES must cost the email, not the student's
# response to an offer already written.
DISPATCH_REMINDER_SES_CONFIG = Config(
    connect_timeout=2,
    read_timeout=3,
    retries={"max_attempts": 1, "mode": "standard"},
)

# Bounded well inside the request's 29 seconds: a slow or throttled invoke leaves the
# stored command to the sweep, not the student to a gateway timeout.
GENERATION_INVOKE_CONFIG = Config(
    connect_timeout=2,
    read_timeout=3,
    retries={"max_attempts": 1, "mode": "standard"},
)

# Rekognition in the moderation region, not the API's own (ADR-010). The API Gateway
# and the Lambda both stop at 29 s, and completion also reads and writes S3. Two
# attempts of at most 2 s connect and 5 s read, plus standard mode's backoff, stay
# near 17 s, so a slow or throttled Rekognition ends as our retryable 503 with
# Retry-After rather than the gateway's bare 504.
IMAGE_MODERATION_CONFIG = Config(
    connect_timeout=2,
    read_timeout=5,
    retries={"mode": "standard", "total_max_attempts": 2},
)

KINDS: Mapping[Kind, Spec] = {
    Kind.S3: Spec("s3", _api_region),
    Kind.S3_PRESIGN: Spec("s3", _api_region, PRESIGN_CONFIG),
    Kind.SES: Spec("ses", _api_region),
    Kind.SES_NOTIFICATION: Spec("sesv2", _api_region),
    # The dispatch reminder is a notification email too (#363), hence SESv2.
    Kind.SES_DISPATCH_REMINDER: Spec("sesv2", _api_region, DISPATCH_REMINDER_SES_CONFIG),
    Kind.COGNITO: Spec("cognito-idp", _api_region),
    Kind.BEDROCK_RUNTIME: Spec("bedrock-runtime", _api_region),
    Kind.LAMBDA: Spec("lambda", _api_region),
    Kind.LAMBDA_GENERATION: Spec("lambda", _api_region, GENERATION_INVOKE_CONFIG),
    Kind.REKOGNITION_MODERATION: Spec(
        "rekognition", _moderation_region, IMAGE_MODERATION_CONFIG
    ),
    Kind.SQS: Spec("sqs", _api_region),
    Kind.WEBSOCKET_MANAGEMENT: Spec(
        "apigatewaymanagementapi", _api_region, needs_endpoint=True
    ),
}


class NotInstalled(LookupError):
    """A test asked for a kind of client it did not install."""

    def __init__(self, kind: Kind) -> None:
        super().__init__(
            f"no AWS client of kind {kind.value!r} is installed for this test; "
            f"call stoa.aws.install({{Kind.{kind.name}: <double>}})"
        )
        self.kind = kind


@dataclass(frozen=True)
class Request:
    """What a call site asked for: the kind, and the region, endpoint and `Config`
    the client would have been built with."""

    kind: Kind
    service: str
    region: str
    endpoint_url: str | None
    config: Config | None


_lock = threading.Lock()
_session: boto3.Session | None = None
_clients: dict[tuple[Kind, str, str | None], Any] = {}
_installed: dict[Kind, Any] | None = None
_requests: list[Request] = []


def session() -> boto3.Session:
    """The one boto3 session every client is built from."""
    global _session
    with _lock:
        if _session is None:
            _session = boto3.Session()
        return _session


def client(
    kind: Kind,
    *,
    region: str | None = None,
    endpoint_url: str | None = None,
    config: Config | None = None,
) -> Any:
    """The client of this kind: a test's double if one is installed, else a real one."""
    kind = Kind(kind)
    spec = KINDS[kind]
    if spec.needs_endpoint and not endpoint_url:
        raise ValueError(f"an AWS client of kind {kind.value!r} needs an endpoint_url")
    resolved_region = region or spec.region(configuration.settings())
    resolved_config = _merged(spec.config, config)
    installed = _installed
    if installed is not None:
        _requests.append(
            Request(kind, spec.service, resolved_region, endpoint_url, resolved_config)
        )
        try:
            return installed[kind]
        except KeyError:
            raise NotInstalled(kind) from None
    if config is not None:
        return _build(spec.service, resolved_region, endpoint_url, resolved_config)
    key = (kind, resolved_region, endpoint_url)
    cached = _clients.get(key)
    if cached is not None:
        return cached
    built = _build(spec.service, resolved_region, endpoint_url, resolved_config)
    with _lock:
        return _clients.setdefault(key, built)


def _merged(base: Config | None, extra: Config | None) -> Config | None:
    if base is None:
        return extra
    if extra is None:
        return base
    return base.merge(extra)


def _build(
    service: str, region: str, endpoint_url: str | None, config: Config | None
) -> Any:
    shared = session()
    kwargs: dict[str, Any] = {"region_name": region}
    if endpoint_url is not None:
        kwargs["endpoint_url"] = endpoint_url
    if config is not None:
        # A copy: botocore rewrites a config's `retries` in place while it builds a
        # client, and the configs in `KINDS` are shared by every caller.
        kwargs["config"] = copy.deepcopy(config)
    # A boto3 session is not safe to build clients from on two threads at once.
    with _lock:
        return shared.client(service, **kwargs)


def install(doubles: Mapping[Kind, Any] | None) -> None:
    """Put a test's doubles where `client` finds them; `None` for real clients again.

    Doubles add to those already installed, so a test may install one kind in a
    fixture and another in its body.
    """
    global _installed
    if doubles is None:
        _installed = None
        return
    merged = dict(_installed or {})
    merged.update({Kind(kind): double for kind, double in doubles.items()})
    _installed = merged


def requests() -> list[Request]:
    """What `client` was asked for since the test's doubles were first installed."""
    return list(_requests)


def reset_for_test() -> None:
    """Nothing installed and nothing recorded: `client` raises until a test installs.

    Called around every test by the autouse fixture in `tests/conftest.py`; the
    clients built for real are dropped too, so none carries one test's credentials or
    moto mock into the next.
    """
    global _installed, _session
    _installed = {}
    _requests.clear()
    with _lock:
        _clients.clear()
        _session = None
