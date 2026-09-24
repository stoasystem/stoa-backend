from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from stoa.config import Settings, get_settings
from stoa.deps import get_current_user
from stoa.routers import auth
from stoa.services import locale_service


def _settings() -> Settings:
    return Settings(
        aws_region="eu-central-2",
        cognito_user_pool_id="pool-id",
        cognito_student_client_id="student-client",
        cognito_parent_client_id="parent-client",
        cognito_teacher_client_id="teacher-client",
        cognito_admin_client_id="admin-client",
    )


def _client(user: dict | None = None) -> TestClient:
    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.dependency_overrides[get_settings] = _settings
    app.dependency_overrides[get_current_user] = lambda: user or {"sub": "student-1", "role": "student"}
    return TestClient(app)


def test_locale_service_resolves_supported_and_missing_values():
    assert locale_service.normalize_locale("de") == "de"
    assert locale_service.normalize_locale("en-US") == "en"
    assert locale_service.normalize_locale("de_CH") == "de"
    assert locale_service.normalize_locale("fr") == "fr"
    assert locale_service.normalize_locale("it") == "it"
    assert locale_service.effective_locale({}) == "de"
    assert locale_service.effective_locale({"language": "en"}) == "en"
    assert locale_service.effective_locale({"preferred_locale": "fr", "language": "de"}) == "fr"


def test_locale_service_rejects_unsupported_and_malformed_values():
    for value in ("es", "zh", "x", "de<script>", ""):
        try:
            locale_service.normalize_locale(value)
        except ValueError:
            continue
        raise AssertionError(f"{value!r} should be rejected")


def test_auth_me_exposes_effective_locale_from_profile(monkeypatch):
    monkeypatch.setattr(
        auth.user_repo,
        "get_user",
        lambda user_id, **_kwargs: {
            "user_id": user_id,
            "email": "student@example.com",
            "name": "Ada",
            "role": "student",
            "preferred_locale": "en",
        },
    )

    response = _client().get("/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["preferredLanguage"] == "en"
    assert body["preferredLocale"] == "en"
    assert body["effectiveLocale"] == "en"
    assert body["role"] == "student"


def test_auth_me_defaults_missing_locale_for_existing_clients(monkeypatch):
    monkeypatch.setattr(
        auth.user_repo,
        "get_user",
        lambda user_id, **_kwargs: {
            "user_id": user_id,
            "email": "student@example.com",
            "name": "Ada",
            "role": "student",
        },
    )

    response = _client().get("/auth/me")

    assert response.status_code == 200
    assert response.json()["effectiveLocale"] == "de"


def test_update_locale_preference_persists_supported_locale(monkeypatch):
    updates = []
    monkeypatch.setattr(
        auth.user_repo,
        "get_user",
        lambda user_id, **_kwargs: {
            "user_id": user_id,
            "email": "student@example.com",
            "name": "Ada",
            "role": "student",
            "language": "de",
        },
    )

    def update_locale(user_id: str, locale: str, updated_at: str):
        updates.append((user_id, locale, updated_at))
        return {
            "user_id": user_id,
            "preferred_locale": locale,
            "preferredLocale": locale,
            "language": locale,
            "locale_updated_at": updated_at,
        }

    monkeypatch.setattr(auth.user_repo, "update_locale_preference", update_locale)

    response = _client().patch("/auth/me/preferences/locale", json={"preferredLocale": "en-US"})

    assert response.status_code == 200
    assert response.json()["preferredLocale"] == "en"
    assert response.json()["effectiveLocale"] == "en"
    assert response.json()["supportedLocales"] == ["de", "en", "fr", "it"]
    assert updates[0][0] == "student-1"
    assert updates[0][1] == "en"


def test_update_locale_preference_persists_newly_supported_locale(monkeypatch):
    updates = []
    monkeypatch.setattr(
        auth.user_repo,
        "get_user",
        lambda user_id, **_kwargs: {
            "user_id": user_id,
            "email": "student@example.com",
            "name": "Ada",
            "role": "student",
            "language": "de",
        },
    )

    def update_locale(user_id: str, locale: str, updated_at: str):
        updates.append((user_id, locale, updated_at))
        return {
            "user_id": user_id,
            "preferred_locale": locale,
            "preferredLocale": locale,
            "language": locale,
            "locale_updated_at": updated_at,
        }

    monkeypatch.setattr(auth.user_repo, "update_locale_preference", update_locale)

    response = _client().patch("/auth/me/preferences/locale", json={"preferredLocale": "fr"})

    assert response.status_code == 200
    assert response.json()["preferredLocale"] == "fr"
    assert response.json()["effectiveLocale"] == "fr"
    assert updates[0][1] == "fr"


def test_update_locale_preference_rejects_unsupported_locale(monkeypatch):
    monkeypatch.setattr(
        auth.user_repo,
        "get_user",
        lambda user_id, **_kwargs: {"user_id": user_id, "email": "student@example.com", "role": "student"},
    )

    response = _client().patch("/auth/me/preferences/locale", json={"preferredLocale": "es"})

    assert response.status_code == 400
    assert response.json()["detail"] == "Unsupported locale"


# ── Accept-Language is negotiated by weight (#20) ───────────────────────────

@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("de;q=0, en;q=1", "en"),
        ("de;q=0,en;q=1", "en"),
        ("fr;q=0.2,en;q=1", "en"),
        ("fr;q=0.2, en", "en"),
        ("en;q=0.8,fr;q=0.8", "en"),
        ("fr;q=0.8,en;q=0.8", "fr"),
        ("de-CH", "de"),
        ("de-CH;q=0.9, zz;q=1", "de"),
        ("en;q=abc,fr", "fr"),
        ("en;q=nan,fr;q=0.1", "fr"),
        ("en;q=1.5,it;q=0.3", "it"),
        ("en;q=-1,it;q=0.3", "it"),
        ("en; q=0.5 , fr ; q=0.7", "fr"),
        ("*;q=1, it;q=0.1", "it"),
        ("en;level=1;q=0.4,fr;q=0.3", "en"),
    ],
)
def test_accept_language_takes_the_heaviest_supported_language(header, expected):
    assert locale_service.locale_from_accept_language(header) == expected


@pytest.mark.parametrize(
    "header",
    ["de;q=0, en;q=0", "de;q=0.0,fr;q=0.000", "zz, xx;q=0.5", "en;q=abc", "*", "", None],
)
def test_accept_language_with_nothing_acceptable_gives_no_locale(header):
    assert locale_service.locale_from_accept_language(header) is None


@pytest.mark.parametrize("locale", ["de", "en", "fr", "it"])
def test_a_single_language_header_is_taken_as_asked(locale):
    assert locale_service.locale_from_accept_language(locale) == locale


@pytest.mark.parametrize("header", [None, "de;q=0, en;q=0"])
def test_without_an_acceptable_request_language_the_profile_decides(header):
    locale_service.set_request_locale(locale_service.locale_from_accept_language(header))
    try:
        assert locale_service.resolve_locale({"preferred_locale": "it"}) == "it"
        assert locale_service.resolve_locale(None) == locale_service.DEFAULT_LOCALE
    finally:
        locale_service.set_request_locale(None)
