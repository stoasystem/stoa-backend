from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MOBILE = ROOT / "mobile"


def read(path: str) -> str:
    return (MOBILE / path).read_text(encoding="utf-8")


def test_notification_api_uses_backend_push_and_event_endpoints() -> None:
    source = read("src/services/notifications/notificationApi.ts")

    for endpoint in [
        "/notifications",
        "/notifications/preferences",
        "/notifications/push-tokens",
        "/read",
        "/archive",
    ]:
        assert endpoint in source

    assert "DELETE" in source
    assert "POST" in source


def test_push_service_uses_expo_project_id_and_permission_states() -> None:
    source = read("src/services/notifications/pushNotifications.ts")

    for symbol in [
        "getPermissionsAsync",
        "requestPermissionsAsync",
        "getExpoPushTokenAsync",
        "config.expoProjectId",
        "provider: \"expo\"",
    ]:
        assert symbol in source

    for state in ["granted", "denied", "unavailable", "provider_blocked"]:
        assert state in read("src/services/notifications/notificationTypes.ts")


def test_deep_links_validate_auth_account_and_role() -> None:
    source = read("src/services/notifications/deepLinks.ts")

    for reason in ["signed_out", "account_blocked", "role_mismatch", "unknown_target"]:
        assert reason in source

    for href in [
        "/student/practice",
        "/student/questions",
        "/parent/children/",
        "/notifications/",
    ]:
        assert href in source


def test_offline_cache_policy_limits_sensitive_categories_and_mutations() -> None:
    source = read("src/services/offline/cachePolicy.ts")

    for category in [
        "raw_prompt",
        "raw_answer",
        "tutoring_transcript",
        "generated_report_artifact",
        "provider_payload",
        "billing_payload",
        "cognito_token_material",
        "private_object_key",
    ]:
        assert category in source

    for mutation in [
        "/questions",
        "/practice/teacher-help",
        "/parents/me/subscription/requests",
        "/parents/me/subscription/billing",
    ]:
        assert mutation in source

    assert "clearOnSignOut: true" in source
    assert "clearOnUserSwitch: true" in source


def test_read_through_cache_uses_sqlite_and_ttl_policy() -> None:
    source = read("src/services/offline/readThroughCache.ts")

    assert "expo-sqlite" in source
    assert "ttlSeconds" in source
    assert "expiresAt" in source
    assert "stale" in source
    assert "clearReadThroughCache" in source


def test_push_offline_docs_record_live_provider_blockers() -> None:
    source = read("docs/PUSH_OFFLINE.md")

    for blocker in ["FCM credentials", "Apple developer/APNs credentials", "Physical-device smoke"]:
        assert blocker in source

    assert "not authorization" in source
