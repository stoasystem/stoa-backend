from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MOBILE = ROOT / "mobile"


def read(path: str) -> str:
    return (MOBILE / path).read_text(encoding="utf-8")


def test_credential_readiness_records_blocked_native_credentials() -> None:
    source = read("src/release/credentialReadiness.ts")

    for key in [
        "expo_project_id",
        "apple_developer_account",
        "google_play_account",
        "fcm_credentials",
        "production_rollout_approval",
    ]:
        assert key in source

    assert "blocked" in source
    assert "safe_fixture_only" in source
    assert "read_only" in source


def test_build_distribution_defines_internal_eas_commands_and_secret_safe_evidence() -> None:
    source = read("src/release/buildDistribution.ts")

    assert "eas build --platform all --profile development" in source
    assert "eas build --platform all --profile preview" in source
    assert "distribution: \"internal\"" in source
    assert "commitSha" in source
    assert "secretSafe: true" in source
    for forbidden in ["private_s3_key", "provider_payload", "cognito"]:
        assert forbidden in source


def test_device_qa_matrix_covers_ios_android_and_required_smoke() -> None:
    source = read("src/release/deviceQa.ts")

    assert "ios_phone" in source
    assert "android_phone" in source
    for smoke in [
        "auth_session_restore",
        "student_dashboard_practice",
        "parent_child_report",
        "push_deep_link",
        "offline_read_through",
        "sign_out_cleanup",
    ]:
        assert smoke in source

    assert "redacted_screenshot" in source
    assert "redacted_log" in source


def test_release_telemetry_is_low_cardinality_and_privacy_guarded() -> None:
    source = read("src/release/releaseTelemetry.ts")

    for signal in [
        "app_started",
        "route_loaded",
        "push_state_changed",
        "offline_state_changed",
        "native_build_blocked",
        "mobile_regression_detected",
    ]:
        assert signal in source

    for forbidden in [
        "raw_prompt",
        "raw_answer",
        "token",
        "provider_payload",
        "billing_payload",
        "free_text",
    ]:
        assert forbidden in source


def test_store_readiness_keeps_launch_out_of_scope_until_approval() -> None:
    source = read("src/release/storeReadiness.ts")
    docs = read("docs/NATIVE_DISTRIBUTION.md")

    for item in [
        "Account ownership",
        "Privacy declarations",
        "Screenshots and review notes",
        "Support staffing",
        "Rollout approval",
    ]:
        assert item in source

    assert "Store launch remains out of scope" in docs
    assert "go/no-go decision" in docs
