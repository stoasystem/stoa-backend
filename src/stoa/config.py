import base64
import binascii
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import re
from typing import Dict, List

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


LOCAL_REPORTS_BUCKET_PLACEHOLDER = "stoa-reports"
PRODUCTION_ENVIRONMENTS = {"production", "prod"}
UPLOAD_INTENT_TTL_SECONDS = 1800
IMAGE_MAX_BYTES = 10 * 1024 * 1024
DOCUMENT_MAX_BYTES = 50 * 1024 * 1024
IMAGE_MAX_EDGE = 4096
FREE_STORAGE_BYTES = 5 * 1024 * 1024 * 1024
PAID_STORAGE_BYTES = 15 * 1024 * 1024 * 1024
DEVELOPMENT_AUDIT_KEY = "stoa-development-authorization-audit-key-change-me"
AUDIT_KEY_MINIMUM_BYTES = 32
_AUDIT_PLACEHOLDER_MARKERS = (
    "changeme",
    "default",
    "development",
    "example",
    "insecure",
    "placeholder",
    "sample",
)


@dataclass(frozen=True, slots=True)
class ValidatedAuthorizationAuditKey:
    key_id: str
    secret: bytes


def _audit_key_error(category: str) -> ValueError:
    """Return a category-only error that is safe to log during startup."""
    return ValueError(f"authorization_audit_key_{category}")


def parse_authorization_audit_secret(secret: str) -> bytes:
    """Decode one audit secret without silently accepting malformed encodings."""
    value = str(secret)
    try:
        if value.startswith("hex:"):
            encoded = value[4:]
            if not encoded or len(encoded) % 2 or not re.fullmatch(r"[0-9a-fA-F]+", encoded):
                raise _audit_key_error("malformed")
            return bytes.fromhex(encoded)
        if value.startswith("base64:"):
            encoded = value[7:]
            if not encoded:
                raise _audit_key_error("malformed")
            return base64.b64decode(encoded, validate=True)
        return value.encode("utf-8")
    except (binascii.Error, UnicodeError) as exc:
        raise _audit_key_error("malformed") from exc


def _has_repeated_pattern(material: bytes) -> bool:
    return any(
        len(material) % width == 0 and material == material[:width] * (len(material) // width)
        for width in range(1, min(8, len(material) // 2) + 1)
    )


def validate_authorization_audit_keyring(
    active_key_id: str,
    active_secret: str,
    previous_keys: Dict[str, str] | None = None,
    *,
    allow_development_default: bool = False,
) -> tuple[ValidatedAuthorizationAuditKey, tuple[ValidatedAuthorizationAuditKey, ...]]:
    """Normalize and validate a unique, 256-bit-or-stronger audit keyring."""
    raw_entries = [(active_key_id, active_secret), *((previous_keys or {}).items())]
    validated: list[ValidatedAuthorizationAuditKey] = []
    key_ids: set[str] = set()
    material_digests: set[bytes] = set()

    for raw_key_id, raw_secret in raw_entries:
        key_id = str(raw_key_id).strip()
        if not key_id:
            raise _audit_key_error("id_missing")
        if key_id in key_ids:
            raise _audit_key_error("id_duplicate")

        secret_text = str(raw_secret)
        if allow_development_default and len(raw_entries) == 1 and secret_text == DEVELOPMENT_AUDIT_KEY:
            material = secret_text.encode("utf-8")
        else:
            material = parse_authorization_audit_secret(secret_text)
            marker_text = "".join(chr(byte).lower() for byte in material if chr(byte).isalnum())
            if len(material) < AUDIT_KEY_MINIMUM_BYTES:
                raise _audit_key_error("weak")
            if len(set(material)) < 8 or _has_repeated_pattern(material):
                raise _audit_key_error("weak")
            if secret_text == DEVELOPMENT_AUDIT_KEY or any(
                marker in marker_text for marker in _AUDIT_PLACEHOLDER_MARKERS
            ):
                raise _audit_key_error("placeholder")

        digest = hashlib.sha256(material).digest()
        if digest in material_digests:
            raise _audit_key_error("material_duplicate")
        key_ids.add(key_id)
        material_digests.add(digest)
        validated.append(ValidatedAuthorizationAuditKey(key_id, material))

    return validated[0], tuple(validated[1:])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        hide_input_in_errors=True,
    )

    # App
    environment: str = "development"
    cors_origins: List[str] = [
        "http://localhost:5173",
        "https://app.stoaedu.ch",
    ]

    # AWS
    aws_region: str = "eu-central-2"
    aws_account_id: str = ""

    # DynamoDB
    dynamodb_table_name: str = "stoa-main"

    # S3
    s3_images_bucket: str = "stoa-images"
    s3_reports_bucket: str = LOCAL_REPORTS_BUCKET_PLACEHOLDER
    s3_presign_expiry_seconds: int = 300
    upload_intent_ttl_seconds: int = UPLOAD_INTENT_TTL_SECONDS
    image_max_bytes: int = IMAGE_MAX_BYTES
    document_max_bytes: int = DOCUMENT_MAX_BYTES
    image_max_edge: int = IMAGE_MAX_EDGE
    free_attachment_storage_bytes: int = FREE_STORAGE_BYTES
    paid_attachment_storage_bytes: int = PAID_STORAGE_BYTES
    immutable_audit_storage_mode: str = "disabled"
    immutable_audit_storage_cdk_managed: bool = False
    immutable_audit_storage_resource: str = ""
    immutable_audit_storage_prefix: str = ""

    # Cognito
    cognito_user_pool_id: str = ""
    cognito_student_client_id: str = ""
    cognito_parent_client_id: str = ""
    cognito_teacher_client_id: str = ""
    cognito_admin_client_id: str = ""
    cognito_allowed_issuers: List[str] = []
    cognito_access_client_ids: List[str] = []
    cognito_jwks_connect_timeout_seconds: float = 2.0
    cognito_jwks_read_timeout_seconds: float = 3.0
    cognito_jwks_ttl_seconds: int = 300
    cognito_jwks_max_stale_seconds: int = 900
    teacher_activation_invitation_expiry_seconds: int = 900

    # Authorization evidence. Production must replace the local-only key.
    authorization_audit_active_key_id: str = "development-v1"
    authorization_audit_active_key: str = DEVELOPMENT_AUDIT_KEY
    authorization_audit_previous_keys: Dict[str, str] = {}
    authorization_audit_probe_window_seconds: int = 300
    authorization_audit_probe_ttl_seconds: int = 86400
    authorization_audit_probe_count_cap: int = 100
    authorization_audit_probe_id_cap: int = 256

    @property
    def allowed_cognito_issuers(self) -> tuple[str, ...]:
        configured = tuple(value.strip().rstrip("/") for value in self.cognito_allowed_issuers)
        if configured:
            return configured
        if not self.cognito_user_pool_id.strip():
            return ()
        return (
            f"https://cognito-idp.{self.aws_region}.amazonaws.com"
            f"/{self.cognito_user_pool_id.strip()}",
        )

    @property
    def allowed_cognito_access_clients(self) -> tuple[str, ...]:
        configured = tuple(value.strip() for value in self.cognito_access_client_ids)
        if configured:
            return configured
        return tuple(
            value.strip()
            for value in (
                self.cognito_student_client_id,
                self.cognito_parent_client_id,
                self.cognito_teacher_client_id,
                self.cognito_admin_client_id,
            )
            if value.strip()
        )

    @model_validator(mode="after")
    def validate_cognito_security_configuration(self) -> "Settings":
        issuers = self.allowed_cognito_issuers
        clients = self.allowed_cognito_access_clients
        if len(set(issuers)) != len(issuers) or len(set(clients)) != len(clients):
            raise ValueError("Cognito issuer and access-client allowlists must be unique")
        if any(not value.startswith("https://") for value in issuers):
            raise ValueError("Cognito issuers must be absolute HTTPS URLs")
        if self.cognito_jwks_connect_timeout_seconds <= 0 or self.cognito_jwks_read_timeout_seconds <= 0:
            raise ValueError("Cognito JWKS timeouts must be positive")
        if self.cognito_jwks_ttl_seconds <= 0:
            raise ValueError("Cognito JWKS TTL must be positive")
        if self.cognito_jwks_max_stale_seconds < self.cognito_jwks_ttl_seconds:
            raise ValueError("Cognito JWKS maximum stale window must be at least its TTL")
        if self.is_production and (not issuers or not clients):
            raise ValueError("Production requires Cognito issuer and access-client allowlists")
        if self.is_production:
            validate_authorization_audit_keyring(
                self.authorization_audit_active_key_id,
                self.authorization_audit_active_key,
                self.authorization_audit_previous_keys,
            )
        else:
            # Local startup keeps the explicit development-only default. Any
            # configured keyring still follows the production parsing contract.
            validate_authorization_audit_keyring(
                self.authorization_audit_active_key_id,
                self.authorization_audit_active_key,
                self.authorization_audit_previous_keys,
                allow_development_default=True,
            )
        if self.authorization_audit_probe_window_seconds <= 0:
            raise ValueError("Authorization audit probe window must be positive")
        if self.authorization_audit_probe_ttl_seconds < self.authorization_audit_probe_window_seconds:
            raise ValueError("Authorization audit probe TTL must cover at least one window")
        if self.authorization_audit_probe_count_cap <= 0 or self.authorization_audit_probe_id_cap <= 0:
            raise ValueError("Authorization audit probe bounds must be positive")
        return self

    @property
    def cognito_jwks_url(self) -> str:
        issuer = self.allowed_cognito_issuers[0] if self.allowed_cognito_issuers else ""
        return f"{issuer}/.well-known/jwks.json"

    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in PRODUCTION_ENVIRONMENTS

    @property
    def report_artifacts_bucket(self) -> str:
        bucket = self.s3_reports_bucket.strip()
        if self.is_production and (
            not bucket or bucket == LOCAL_REPORTS_BUCKET_PLACEHOLDER
        ):
            raise ValueError(
                "S3_REPORTS_BUCKET must be configured by CDK in production"
            )
        return bucket or LOCAL_REPORTS_BUCKET_PLACEHOLDER

    # Bedrock
    # EU cross-region inference profile — no manual model access approval needed
    bedrock_model_id: str = "eu.anthropic.claude-sonnet-4-6"
    bedrock_max_tokens: int = 2048

    # Limits (per role per day)
    free_tier_daily_question_limit: int = 5
    standard_tier_daily_question_limit: int = 30
    premium_tier_daily_question_limit: int = 100

    # Conversation message limits per day. Free users get enough room for a
    # first simple exchange; paid tiers keep the broader product allowance.
    free_tier_daily_chat_message_limit: int = 8
    standard_tier_daily_chat_message_limit: int = 80
    premium_tier_daily_chat_message_limit: int = 200

    # Legacy fallback for code paths that do not yet resolve plan entitlements.
    daily_chat_message_limit: int = 80

    # Practice hint limits per day
    free_tier_daily_hint_limit: int = 2
    standard_tier_daily_hint_limit: int = 30
    premium_tier_daily_hint_limit: int = 80

    # Legacy fallback for code paths that do not yet resolve plan entitlements.
    daily_hint_limit: int = 30

    # SQS
    teacher_queue_url: str = ""

    # Lambda targets
    weekly_report_function_name: str = "stoa-weekly-report"

    # WebSocket realtime notifications
    websocket_api_endpoint: str = ""
    websocket_connection_ttl_seconds: int = 600
    websocket_live_routes_configured: bool = False
    websocket_live_connect_route: str = "$connect"
    websocket_live_disconnect_route: str = "$disconnect"
    websocket_live_message_route: str = "message"
    websocket_live_deployed: bool = False
    websocket_live_smoke_passed: bool = False
    websocket_stale_cleanup_enabled: bool = True

    # Provider-backed notifications (v4.9)
    notification_email_provider: str = ""
    notification_email_provider_approved: bool = False
    notification_email_sender: str = "noreply@stoaedu.ch"
    notification_email_digest_template: str = "notification_digest_v1"
    notification_email_send_enabled: bool = False
    notification_push_provider: str = ""
    notification_push_provider_approved: bool = False
    notification_push_provider_api_key: str = ""
    notification_push_provider_endpoint_url: str = ""
    notification_push_template: str = "notification_push_v1"
    notification_push_send_enabled: bool = False

    # Payment provider integration (v3.9)
    stripe_api_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_standard_price_id: str = ""
    stripe_premium_price_id: str = ""
    stripe_webhook_endpoint_url: str = ""
    stripe_checkout_success_url: str = "http://localhost:5173/parent/subscription?checkout=success"
    stripe_checkout_cancel_url: str = "http://localhost:5173/parent/subscription?checkout=cancel"
    stripe_live_charges_enabled: bool = False
    stripe_refunds_enabled: bool = False
    stripe_twint_enabled: bool = True
    stripe_twint_capability_confirmed: bool = False
    stripe_allow_unsigned_test_webhooks: bool = False

    # Support handoff delivery (v4.5)
    support_internal_queue_approved: bool = False
    support_third_party_provider_approved: bool = False
    support_third_party_provider_api_key: str = ""
    support_third_party_provider_endpoint_url: str = ""
    support_third_party_provider_fail_delivery: bool = False
    support_crm_messaging_approved: bool = False
    support_crm_destination_approved: bool = False
    support_crm_fail_delivery: bool = False
    support_crm_approved_templates: List[str] = [
        "support_receipt",
        "status_update",
        "resolution",
        "escalation",
    ]
    support_crm_opt_out_delivery_ids: List[str] = []

    # BI / observability activation (v5.18)
    bi_warehouse_live_configured: bool = False
    bi_warehouse_export_enabled: bool = False
    apm_provider: str = ""
    apm_alert_destination_approved: bool = False
    apm_alerts_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
