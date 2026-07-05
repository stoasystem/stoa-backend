from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MOBILE = ROOT / "mobile"


def read(path: str) -> str:
    return (MOBILE / path).read_text(encoding="utf-8")


def test_auth_uses_amplify_session_restore_and_cognito_flows() -> None:
    source = read("src/services/auth/amplifyAuth.ts")

    for symbol in [
        "Amplify.configure",
        "fetchAuthSession",
        "getCurrentUser",
        "signIn",
        "signUp",
        "confirmSignUp",
        "resendSignUpCode",
        "signOut",
    ]:
        assert symbol in source

    assert "loginWith" in source
    assert "email: true" in source


def test_auth_services_do_not_use_web_local_storage() -> None:
    service_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (MOBILE / "src/services").rglob("*.ts")
    )

    assert "localStorage" not in service_sources
    assert "window.localStorage" not in service_sources


def test_secure_store_only_persists_session_metadata() -> None:
    source = read("src/services/auth/secureSessionMetadata.ts")

    assert "expo-secure-store" in source
    assert "LAST_SIGNED_IN_EMAIL_KEY" in source
    assert "LAST_ROLE_KEY" in source

    forbidden_token_keys = ["ACCESS_TOKEN", "ID_TOKEN", "REFRESH_TOKEN", "COGNITO_TOKEN"]
    for token_key in forbidden_token_keys:
        assert token_key not in source


def test_account_state_mapper_covers_support_safe_states() -> None:
    source = read("src/services/auth/accountState.ts")

    for account_state in [
        "verification_required",
        "session_expired",
        "entitlement_required",
        "billing_action_required",
        "child_binding_required",
        "quota_exhausted",
        "provider_blocked",
        "unauthorized",
        "forbidden",
        "unknown",
    ]:
        assert account_state in source

    assert "supportCode" in source


def test_api_client_attaches_bearer_token_from_auth_service() -> None:
    source = read("src/services/api/mobileApiClient.ts")

    assert "getAccessToken" in source
    assert "Authorization" in source
    assert "Bearer ${accessToken}" in source
    assert "MobileApiError" in source


def test_sign_out_cleanup_clears_cache_metadata_and_push_hook() -> None:
    source = read("src/services/auth/signOutCleanup.ts")

    assert "queryClient.clear()" in source
    assert "clearSessionMetadata" in source
    assert "revokePushToken" in source
    assert "signOutOfStoa" in source
