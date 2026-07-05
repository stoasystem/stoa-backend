from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MOBILE = ROOT / "mobile"


def read_text(path: str) -> str:
    return (MOBILE / path).read_text(encoding="utf-8")


def test_mobile_package_declares_native_stack() -> None:
    package = json.loads(read_text("package.json"))
    deps = package["dependencies"]

    assert deps["expo"].startswith("~57.")
    assert deps["react-native"] == "0.86.0"
    assert deps["react"] == "19.2.3"

    for dependency in [
        "expo-router",
        "aws-amplify",
        "@aws-amplify/react-native",
        "@tanstack/react-query",
        "expo-notifications",
        "expo-secure-store",
        "expo-sqlite",
    ]:
        assert dependency in deps


def test_mobile_app_declares_deep_link_and_internal_build_contract() -> None:
    app = json.loads(read_text("app.json"))["expo"]
    eas = json.loads(read_text("eas.json"))

    assert app["scheme"] == "stoa"
    assert app["ios"]["bundleIdentifier"] == "com.stoa.mobile"
    assert app["android"]["package"] == "com.stoa.mobile"
    assert eas["build"]["preview"]["distribution"] == "internal"


def test_mobile_route_groups_cover_required_surfaces() -> None:
    routes = read_text("src/navigation/routes.ts")

    for route_group in [
        "AUTH_ROUTES",
        "STUDENT_ROUTES",
        "PARENT_ROUTES",
        "NOTIFICATION_ROUTES",
        "BLOCKED_ROUTES",
    ]:
        assert route_group in routes

    for path in [
        "/auth/sign-in",
        "/student/practice",
        "/student/questions",
        "/parent/children/[childId]/report",
        "/notifications/[eventId]",
        "/blocked/provider",
    ]:
        assert path in routes


def test_mobile_environment_contract_defaults_no_demo_fallback() -> None:
    config = read_text("src/config/mobileConfig.ts")

    for env_name in [
        "EXPO_PUBLIC_STOA_API_BASE_URL",
        "EXPO_PUBLIC_STOA_COGNITO_REGION",
        "EXPO_PUBLIC_STOA_COGNITO_USER_POOL_ID",
        "EXPO_PUBLIC_STOA_COGNITO_CLIENT_ID",
        "EXPO_PUBLIC_STOA_EXPO_PROJECT_ID",
        "EXPO_PUBLIC_STOA_NO_DEMO_FALLBACK",
    ]:
        assert env_name in config

    assert 'process.env.EXPO_PUBLIC_STOA_NO_DEMO_FALLBACK !== "false"' in config
