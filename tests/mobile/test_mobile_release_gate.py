from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MOBILE = ROOT / "mobile"


def read(path: str) -> str:
    return (MOBILE / path).read_text(encoding="utf-8")


def test_release_evidence_records_source_ready_state_and_verification() -> None:
    source = read("docs/RELEASE_EVIDENCE.md")

    assert "native-mobile-source-ready-local" in source
    assert "pytest tests/mobile" in source
    assert "26 passed" in source


def test_release_evidence_keeps_live_native_blockers_explicit() -> None:
    source = read("docs/RELEASE_EVIDENCE.md")

    for blocker in [
        "Mobile dependencies were declared but not installed",
        "Expo native build was not run",
        "Physical-device iOS/Android QA was not run",
        "Live push delivery smoke was not run",
        "Public App Store or Play Store launch was not attempted",
    ]:
        assert blocker in source


def test_release_evidence_names_provider_prerequisites() -> None:
    source = read("docs/RELEASE_EVIDENCE.md")

    for prerequisite in [
        "Expo project ID",
        "FCM credentials",
        "APNs credentials",
        "physical-device matrix",
        "store assets",
    ]:
        assert prerequisite in source


def test_release_evidence_preserves_privacy_and_no_demo_fallback() -> None:
    source = read("docs/RELEASE_EVIDENCE.md")

    assert "EXPO_PUBLIC_STOA_NO_DEMO_FALLBACK" in source
    assert "no fixture user IDs or demo responses" in source
    for forbidden in [
        "raw prompts",
        "answers",
        "provider payloads",
        "billing payloads",
        "Cognito token material",
        "private object keys",
    ]:
        assert forbidden in source
