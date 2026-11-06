"""The curriculum console and the usage card read codes, not English (#277).

- A refused curriculum request is a rule violation, `{detail: {code, message,
  correlationId}}`, not a bare string `{detail: "stale_pointer"}` (#211).
- Each line of the validation report carries an issue `code` and its `params`
  beside the English `message` (#112).
- A usage reconciliation carries `explanationCode` and `explanationParams`
  beside the English `explanation` (#114).
"""

from __future__ import annotations

import json
from string import Formatter

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from actor_helpers import install_actor_overrides
from rule_violation_helpers import assert_violation
from stoa.routers import admin
from stoa.rule_violation import RuleViolation, registered_codes, violation_response
from stoa.services import (
    curriculum_ops_service,
    locale_service,
    message_catalog,
    usage_ledger_service,
)
from stoa.services.curriculum_errors import CurriculumErrorCode
from stoa.services.curriculum_issues import Issue, IssueCode, catalog_key
from stoa.services.usage_ledger_service import ReconciliationExplanation

LOCALES = sorted(locale_service.SUPPORTED_LOCALES)


def _params(template: str) -> set[str]:
    return {name for _, name, _, _ in Formatter().parse(template) if name}


def _keys(prefix: str) -> set[str]:
    return {key for key in message_catalog.TEXT if key.startswith(prefix)}


# ── the catalog ──────────────────────────────────────────────────────────────

_TABLES = [
    ("curriculum_issue.", {catalog_key(code) for code in IssueCode}),
    ("reconciliation.", {f"reconciliation.{code}" for code in ReconciliationExplanation}),
]


@pytest.mark.parametrize(("prefix", "expected"), _TABLES)
def test_every_code_has_exactly_one_catalog_key(prefix: str, expected: set[str]) -> None:
    assert _keys(prefix) == expected


@pytest.mark.parametrize(
    "key", sorted(_keys("curriculum_issue.") | _keys("reconciliation."))
)
def test_every_key_has_four_languages_with_the_same_params_and_swiss_ss(key: str) -> None:
    variants = message_catalog.TEXT[key]
    assert set(variants) == set(LOCALES)
    assert all(variants[locale].strip() for locale in LOCALES)
    assert len({frozenset(_params(variants[locale])) for locale in LOCALES}) == 1, variants
    assert "ß" not in variants["de"]


def test_the_curriculum_codes_are_registered_under_their_old_names() -> None:
    registered = {value for value, (domain, _) in registered_codes().items() if domain == "curriculum"}
    assert registered == {code.value for code in CurriculumErrorCode}
    assert "stale_pointer" in registered and "validation_failed" in registered


# ── refusals ─────────────────────────────────────────────────────────────────


def _client(capabilities: tuple[str, ...], **headers: str) -> TestClient:
    app = FastAPI()
    app.include_router(admin.router, prefix="/admin")
    install_actor_overrides(
        app,
        {
            "sub": "operator-1",
            "role": "teacher",
            "capabilities": {capability: "granted" for capability in capabilities},
        },
    )
    return TestClient(app, headers=headers)


def test_a_missing_capability_is_a_rule_violation_in_the_reader_language() -> None:
    # The route lets a teacher through; the service decides the capability.
    with pytest.raises(RuleViolation) as refused:
        curriculum_ops_service.validation_preview("lesson-x", "v1", {"sub": "t", "role": "teacher"})

    response = violation_response(refused.value, locale="fr")
    assert response.status_code == 403
    assert json.loads(response.body)["detail"] == {
        "code": "curriculum_capability_required",
        "message": message_catalog.TEXT["error.curriculum_capability_required"]["fr"],
        "correlationId": response.headers["X-Correlation-ID"],
    }


def test_a_missing_version_is_no_longer_a_bare_string(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(curriculum_ops_service.curriculum_ops_repo, "get_version", lambda *_: None)
    client = _client((curriculum_ops_service.AUTHOR_CAPABILITY,))

    response = client.post(
        "/admin/curriculum/lessons/lesson-x/drafts/v-gone/validation-preview"
    )

    assert not isinstance(response.json()["detail"], str)
    assert_violation(response, CurriculumErrorCode.CURRICULUM_VERSION_NOT_FOUND)


def test_a_refused_draft_names_its_fields() -> None:
    with pytest.raises(RuleViolation) as refused:
        curriculum_ops_service._clean_id("  ")  # noqa: SLF001

    assert refused.value.code is CurriculumErrorCode.VALIDATION_FAILED
    assert refused.value.public_body("en")["fields"] == ["id"]


# ── the validation report ────────────────────────────────────────────────────


def test_an_issue_carries_its_code_params_and_english_sentence() -> None:
    line = curriculum_ops_service._validation_issue(  # noqa: SLF001
        "exercises[0].skills",
        Issue.of(IssueCode.SKILL_IN_ANOTHER_UNIT, skill="s", unit="u2", lesson_unit="u1"),
    )

    assert line == {
        "severity": "blocking",
        "field": "exercises[0].skills",
        "code": "skill_in_another_unit",
        "params": {"skill": "s", "unit": "u2", "lesson_unit": "u1"},
        "message": "Skill 's' belongs to unit 'u2', not 'u1'.",
        "hint": "Provide this field before submitting or publishing the draft.",
    }


def test_the_same_issue_reads_in_every_language() -> None:
    issue = Issue.of(IssueCode.TRANSLATION_LOCALE_UNSUPPORTED, language="es")

    assert issue.message() == "Unsupported locale 'es'."
    assert issue.message("de") == "Nicht unterstützte Sprache «es»."


def test_a_lesson_report_is_all_codes() -> None:
    issues = curriculum_ops_service._validation_issues(  # noqa: SLF001
        {"lesson_id": "l1"},
        [{"type": "multiple_choice", "options": ["1"], "answer_key": "1",
          "translations": {"es": {"prompt": "?"}}}],
        level="publish",
    )

    codes = {issue["code"] for issue in issues}
    assert {"lesson_field_missing", "unit_missing", "too_few_options",
            "translation_locale_unsupported", "exercise_field_missing"} <= codes
    assert all(issue["message"] == Issue.of(IssueCode(issue["code"]), **issue["params"]).message()
               for issue in issues)


# ── the usage reconciliation ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("status", "stale", "code", "params", "explanation"),
    [
        ("matched", False, "counter_matches_ledger", {},
         "Counter and usage ledger match for this quota period."),
        ("no-usage", False, "no_usage", {}, "No usage was recorded for this action and quota period."),
        ("ledger-only", False, "ledger_only", {},
         "This support-visible action is tracked only in the ledger and has no quota counter."),
        ("over-limit", False, "counter_over_limit", {"counter": 3, "limit": 2},
         "Counter value 3 is above the entitlement limit 2; review quota enforcement and recent "
         "retries before changing access."),
        ("stale", True, "counter_stale", {},
         "The counter row appears stale for this quota period; verify TTL behavior before using it "
         "for support decisions."),
        ("ledger-missing", False, "counter_without_ledger", {"counter": 3},
         "Counter shows 3 consumed but no matching ledger events were found."),
        ("counter-missing", False, "ledger_without_counter", {"ledger": 1},
         "Ledger shows 1 consumed but no matching counter row was found."),
        ("count-mismatch", False, "count_mismatch", {"counter": 3, "ledger": 1},
         "Counter value 3 and ledger total 1 do not match."),
    ],
)
def test_each_reconciliation_has_a_code_and_keeps_its_english(
    status: str, stale: bool, code: str, params: dict, explanation: str
) -> None:
    support = usage_ledger_service._reconciliation_support_state(  # noqa: SLF001
        status=status, counter_count=3, ledger_count=1, limit=2, stale=stale
    )

    assert support["explanationCode"] == code
    assert support["explanationParams"] == params
    assert support["explanation"] == explanation
