from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import re
from typing import NamedTuple, Protocol, Sequence
from urllib.parse import urlencode, urlsplit, urlunsplit


CHECKOUT_RESULT_PATH = "/billing/checkout/result"
_DEVELOPMENT_ENVIRONMENTS = frozenset({"dev", "development", "local", "test"})
_STAGING_ENVIRONMENTS = frozenset({"stage", "staging"})
_PRODUCTION_ENVIRONMENTS = frozenset({"prod", "production"})
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_OPAQUE_CHECKOUT_REFERENCE = re.compile(r"[A-Za-z0-9_-]{8,128}")
_DNS_HOST = re.compile(
    r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)


class BillingCallbackSettings(Protocol):
    environment: str
    stripe_checkout_web_origins: Sequence[str]
    stripe_checkout_result_path: str


class CheckoutReturnUrls(NamedTuple):
    success_url: str
    cancel_url: str


def _environment_kind(environment: str) -> str:
    normalized = environment.strip().lower()
    if normalized in _DEVELOPMENT_ENVIRONMENTS:
        return "development"
    if normalized in _STAGING_ENVIRONMENTS:
        return "staging"
    if normalized in _PRODUCTION_ENVIRONMENTS:
        return "production"
    raise ValueError("billing_web_origin_environment_invalid")


def _canonical_netloc(host: str, port: int | None) -> str:
    rendered_host = f"[{host}]" if ":" in host else host
    return f"{rendered_host}:{port}" if port is not None else rendered_host


def parse_exact_web_origin(configured: str, *, environment: str) -> str:
    """Validate and canonicalize one trusted, current-environment Web origin."""
    if not isinstance(configured, str) or not configured or configured != configured.strip():
        raise ValueError("billing_web_origin_invalid")
    if any(character in configured for character in ("%", "\\", "@", "*")):
        raise ValueError("billing_web_origin_ambiguous")
    if any(ord(character) < 0x21 or ord(character) == 0x7F for character in configured):
        raise ValueError("billing_web_origin_ambiguous")

    try:
        parsed = urlsplit(configured)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("billing_web_origin_invalid") from exc

    if (
        not parsed.scheme
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or parsed.netloc.endswith(":")
    ):
        raise ValueError("billing_web_origin_must_be_origin")

    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if (
        not host
        or host.endswith(".")
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError("billing_web_origin_invalid")

    kind = _environment_kind(environment)
    is_loopback = host in _LOOPBACK_HOSTS
    if kind == "development":
        if scheme not in {"http", "https"} or not is_loopback or port is None:
            raise ValueError("billing_web_origin_development_loopback_required")
    else:
        if scheme != "https":
            raise ValueError("billing_web_origin_https_required")
        if is_loopback:
            raise ValueError("billing_web_origin_loopback_forbidden")
        if port not in {None, 443}:
            raise ValueError("billing_web_origin_port_forbidden")
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if _DNS_HOST.fullmatch(host) is None:
                raise ValueError("billing_web_origin_host_invalid")
        else:
            raise ValueError("billing_web_origin_host_invalid")

    canonical_port = None if scheme == "https" and port == 443 else port
    canonical = urlunsplit(
        (scheme, _canonical_netloc(host, canonical_port), "", "", "")
    )
    if urlsplit(canonical).hostname != host:
        raise ValueError("billing_web_origin_ambiguous")
    return canonical


@dataclass(frozen=True, slots=True)
class BillingWebOriginPolicy:
    environment: str
    configured_origins: tuple[str, ...]
    result_path: str

    def __post_init__(self) -> None:
        if self.result_path != CHECKOUT_RESULT_PATH:
            raise ValueError("billing_checkout_result_path_invalid")
        if not self.configured_origins:
            raise ValueError("billing_web_origin_missing")

        canonical = tuple(
            parse_exact_web_origin(origin, environment=self.environment)
            for origin in self.configured_origins
        )
        if len(set(canonical)) != len(canonical):
            raise ValueError("billing_web_origin_duplicate")
        object.__setattr__(self, "configured_origins", canonical)

    @classmethod
    def from_settings(
        cls,
        settings: BillingCallbackSettings,
    ) -> BillingWebOriginPolicy:
        origins = settings.stripe_checkout_web_origins
        if isinstance(origins, (str, bytes)):
            raise ValueError("billing_web_origin_invalid")
        return cls(
            environment=settings.environment,
            configured_origins=tuple(origins),
            result_path=settings.stripe_checkout_result_path,
        )

    @property
    def callback_origin(self) -> str:
        """Return the server-selected primary origin from ordered configuration."""
        return self.configured_origins[0]

    def require_configured_origin(self, candidate: str) -> str:
        """Require structural equality with one configured origin."""
        try:
            canonical = parse_exact_web_origin(
                candidate,
                environment=self.environment,
            )
        except ValueError as exc:
            raise ValueError("billing_web_origin_unconfigured") from exc
        if canonical not in self.configured_origins:
            raise ValueError("billing_web_origin_unconfigured")
        return canonical


def build_checkout_return_urls(
    checkout_ref: str,
    settings: BillingCallbackSettings,
) -> CheckoutReturnUrls:
    """Build Stripe navigation URLs exclusively from server configuration."""
    if (
        not isinstance(checkout_ref, str)
        or _OPAQUE_CHECKOUT_REFERENCE.fullmatch(checkout_ref) is None
    ):
        raise ValueError("billing_checkout_reference_invalid")

    policy = BillingWebOriginPolicy.from_settings(settings)

    def build(flow: str) -> str:
        query = urlencode({"checkoutRef": checkout_ref, "flow": flow})
        origin = urlsplit(policy.callback_origin)
        return urlunsplit(
            (
                origin.scheme,
                origin.netloc,
                policy.result_path,
                query,
                "",
            )
        )

    return CheckoutReturnUrls(
        success_url=build("return"),
        cancel_url=build("cancel"),
    )
