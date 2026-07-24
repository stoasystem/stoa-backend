from __future__ import annotations

import ast
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from stoa.config import FREE_STORAGE_BYTES, PAID_STORAGE_BYTES, Settings, get_settings
from stoa.models.billing import BillingPlanId
from stoa.models.user import SubscriptionTier, UserProfile
from stoa.routers import auth


CANONICAL_PLAN_VALUES = {
    "free_trial",
    "student",
    "teacher_supported",
    "family",
}
LEGACY_PLAN_VALUES = {"free", "standard", "premium", "tutor_supported"}
AUTH_PATH = Path("src/stoa/routers/auth.py")
CONFIG_PATH = Path("src/stoa/config.py")
ENV_EXAMPLE_PATH = Path(".env.example")


def _literal_dict_writes(path: Path, field_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    writes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        entries = {
            key.value: value
            for key, value in zip(node.keys, node.values, strict=True)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        value = entries.get(field_name)
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            writes.add(value.value)
    return writes


def _cognito_subscription_attribute_writes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    writes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        entries = {
            key.value: value
            for key, value in zip(node.keys, node.values, strict=True)
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        name = entries.get("Name")
        value = entries.get("Value")
        if (
            isinstance(name, ast.Constant)
            and name.value == "custom:subscription_tier"
            and isinstance(value, ast.Constant)
            and isinstance(value.value, str)
        ):
            writes.add(value.value)
    return writes


def _example_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        values[name] = value
    return values


def test_subscription_and_billing_plan_types_have_one_byte_identical_value_set() -> None:
    subscription_values = {tier.value for tier in SubscriptionTier}
    billing_values = {plan.value for plan in BillingPlanId}

    assert subscription_values == billing_values == CANONICAL_PLAN_VALUES
    assert set(SubscriptionTier.__members__) == {
        "FREE_TRIAL",
        "STUDENT",
        "TEACHER_SUPPORTED",
        "FAMILY",
    }
    assert subscription_values.isdisjoint(LEGACY_PLAN_VALUES)
    assert (
        UserProfile.model_fields["subscription_tier"].default
        is SubscriptionTier.FREE_TRIAL
    )


def test_settings_expose_exact_paid_price_identity_without_compatibility_aliases() -> None:
    settings_fields = set(Settings.model_fields)
    paid_price_fields = {
        field
        for field in settings_fields
        if field.startswith("stripe_") and field.endswith("_price_id")
    }

    assert paid_price_fields == {
        "stripe_student_price_id",
        "stripe_teacher_supported_price_id",
        "stripe_family_price_id",
    }
    assert "stripe_standard_price_id" not in settings_fields
    assert "stripe_premium_price_id" not in settings_fields
    assert all("tutor" not in field for field in paid_price_fields)


def test_plan_settings_lock_trial_storage_and_sandbox_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.free_trial_days == 14
    assert settings.free_attachment_storage_bytes == FREE_STORAGE_BYTES == 5 * 1024**3
    assert settings.paid_attachment_storage_bytes == PAID_STORAGE_BYTES == 15 * 1024**3
    assert settings.stripe_live_charges_enabled is False


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("free_trial_days", 13, "free_trial_days_locked"),
        (
            "free_attachment_storage_bytes",
            FREE_STORAGE_BYTES - 1,
            "free_attachment_storage_bytes_locked",
        ),
        (
            "paid_attachment_storage_bytes",
            PAID_STORAGE_BYTES + 1,
            "paid_attachment_storage_bytes_locked",
        ),
    ],
)
def test_trial_and_storage_contract_cannot_be_reconfigured(
    field: str,
    value: int,
    error: str,
) -> None:
    with pytest.raises(ValidationError, match=error):
        Settings(_env_file=None, **{field: value})


def test_checkout_configuration_requires_three_distinct_paid_prices() -> None:
    configured = Settings(
        _env_file=None,
        stripe_api_key="sk_test_plan_identity",
        stripe_student_price_id="price_student_test",
        stripe_teacher_supported_price_id="price_teacher_supported_test",
        stripe_family_price_id="price_family_test",
    )
    assert {
        configured.stripe_student_price_id,
        configured.stripe_teacher_supported_price_id,
        configured.stripe_family_price_id,
    } == {
        "price_student_test",
        "price_teacher_supported_test",
        "price_family_test",
    }

    with pytest.raises(ValidationError, match="stripe_paid_price_ids_missing"):
        Settings(
            _env_file=None,
            stripe_api_key="sk_test_plan_identity",
            stripe_student_price_id="price_student_test",
            stripe_teacher_supported_price_id="price_teacher_supported_test",
        )

    with pytest.raises(ValidationError, match="stripe_paid_price_ids_duplicate"):
        Settings(
            _env_file=None,
            stripe_api_key="sk_test_plan_identity",
            stripe_student_price_id="price_shared_test",
            stripe_teacher_supported_price_id="price_shared_test",
            stripe_family_price_id="price_family_test",
        )


@pytest.mark.parametrize("environment", ["development", "test"])
def test_nonproduction_settings_reject_live_keys_and_charge_mode(environment: str) -> None:
    paid_prices = {
        "stripe_student_price_id": "price_student_test",
        "stripe_teacher_supported_price_id": "price_teacher_supported_test",
        "stripe_family_price_id": "price_family_test",
    }

    with pytest.raises(ValidationError, match="stripe_live_api_key_forbidden"):
        Settings(
            _env_file=None,
            environment=environment,
            stripe_api_key="sk_live_forbidden_canary",
            **paid_prices,
        )

    with pytest.raises(ValidationError, match="stripe_live_charges_forbidden"):
        Settings(
            _env_file=None,
            environment=environment,
            stripe_api_key="sk_test_plan_identity",
            stripe_live_charges_enabled=True,
            **paid_prices,
        )


def test_active_profile_writes_use_only_free_trial_semantics() -> None:
    active_writes = _literal_dict_writes(
        AUTH_PATH, "subscription_tier"
    ) | _cognito_subscription_attribute_writes(AUTH_PATH)

    assert active_writes == {"free_trial"}
    assert active_writes.isdisjoint(LEGACY_PLAN_VALUES)

    # Cosmetic/legacy daily counters can still contain English tier words; they
    # are intentionally outside the active enum, Price, and profile-write inventory.
    config_source = CONFIG_PATH.read_text(encoding="utf-8")
    assert "standard_tier_daily_question_limit" in config_source
    assert "premium_tier_daily_question_limit" in config_source


@pytest.mark.parametrize("role", ["student", "parent"])
def test_new_public_account_profiles_and_provider_attributes_start_free_trial(
    monkeypatch: pytest.MonkeyPatch,
    role: str,
) -> None:
    stored: dict[str, object] = {}
    provider_calls: list[dict[str, object]] = []

    class FakeCognito:
        def sign_up(self, **kwargs):
            return {"UserSub": f"{role}-subject"}

        def admin_update_user_attributes(self, **kwargs):
            provider_calls.append(kwargs)
            return {}

    def start_registration(**kwargs):
        stored.update(kwargs["profile"])
        return object(), dict(stored)

    monkeypatch.setattr(auth, "_get_cognito", lambda settings: FakeCognito())
    monkeypatch.setattr(
        auth.public_identity_service,
        "start_or_resume_public_registration",
        start_registration,
    )

    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None,
        cognito_user_pool_id="pool-id",
        cognito_student_client_id="public-client-id",
    )

    response = TestClient(app).post(
        "/auth/register",
        json={
            "email": f"{role}@example.com",
            "password": "ValidPass123!",
            "role": role,
        },
    )

    assert response.status_code == 201
    assert stored["subscription_tier"] == "free_trial"
    assert provider_calls == [
        {
            "UserPoolId": "pool-id",
            "Username": f"{role}@example.com",
            "UserAttributes": [
                {"Name": "custom:subscription_tier", "Value": "free_trial"}
            ],
        }
    ]


def test_environment_example_names_every_plan_setting_without_live_secrets() -> None:
    example = _example_values()

    assert example["STRIPE_STUDENT_PRICE_ID"] == ""
    assert example["STRIPE_TEACHER_SUPPORTED_PRICE_ID"] == ""
    assert example["STRIPE_FAMILY_PRICE_ID"] == ""
    assert example["STRIPE_API_KEY"] == ""
    assert example["STRIPE_WEBHOOK_SECRET"] == ""
    assert example["STRIPE_LIVE_CHARGES_ENABLED"].lower() == "false"
    assert example["FREE_TRIAL_DAYS"] == "14"
    assert example["FREE_ATTACHMENT_STORAGE_BYTES"] == str(5 * 1024**3)
    assert example["PAID_ATTACHMENT_STORAGE_BYTES"] == str(15 * 1024**3)
    assert "sk_live_" not in ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
