from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MOBILE = ROOT / "mobile"


def read(path: str) -> str:
    return (MOBILE / path).read_text(encoding="utf-8")


def test_student_api_uses_real_backend_endpoints() -> None:
    source = read("src/features/student/studentApi.ts")

    for endpoint in [
        "/students/me/profile",
        "/practice/overview",
        "/practice/curriculum/catalog",
        "/practice/curriculum/progress",
        "/practice/curriculum/lessons/",
        "/questions",
        "/request-teacher",
        "/practice/teacher-help",
        "/notifications",
    ]:
        assert endpoint in source

    assert "idempotency_key" in source


def test_parent_api_uses_real_backend_endpoints() -> None:
    source = read("src/features/parent/parentApi.ts")

    for endpoint in [
        "/parents/me/children",
        "/parents/me/subscription",
        "/parents/me/subscription/billing",
        "/parents/me/account-operations",
        "/summary",
        "/learning-profile",
        "/usage",
        "/history",
        "/report",
        "/notifications",
    ]:
        assert endpoint in source


def test_journey_state_supports_mobile_screen_states_and_account_mapping() -> None:
    source = read("src/services/journeys/journeyState.ts")

    for state in ["loading", "ready", "empty", "blocked", "stale", "error"]:
        assert state in source

    assert "accountStateFromApiError" in source
    assert "MobileApiError" in source


def test_student_and_parent_screen_contracts_define_offline_and_online_boundaries() -> None:
    student = read("src/features/student/studentScreens.ts")
    parent = read("src/features/parent/parentScreens.ts")
    combined = f"{student}\n{parent}"

    for route in [
        "/student/practice",
        "/student/questions",
        "/parent/children/[childId]/report",
        "/parent/billing",
    ]:
        assert route in combined

    assert "offlineReadThrough: true" in combined
    assert "offlineReadThrough: false" in combined
    assert "onlineOnlyMutations" in combined


def test_mobile_copy_covers_english_and_chinese_journey_labels() -> None:
    source = read("src/i18n/mobileCopy.ts")

    for key in [
        "practice",
        "askQuestion",
        "learningHistory",
        "childSummary",
        "childHistory",
        "childReport",
        "billing",
    ]:
        assert key in source

    assert "学生主页" in source
    assert "家长主页" in source


def test_journey_docs_reject_demo_data() -> None:
    source = read("docs/JOURNEYS.md")

    assert "Demo data" in source
    assert "not allowed" in source
