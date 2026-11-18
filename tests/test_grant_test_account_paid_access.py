"""The operator tool that gives a linked test student paid access, against the fake table.

`scripts/grant_test_account_paid_access.py` replaced `enable_teacher_support_testing.py`,
which looked accounts up by Cognito subject (user ids are no longer subjects), wrote
the grant with a hand-built `put_item`, and in the same run put the test teacher into
live dispatch. What these hold:

- the grant it writes is the one the app's own readers accept: the grant read, the
  entitlement, the token reservation and the teacher-support admission;
- every precondition refuses on its own, and a refusal writes nothing;
- a dry run writes nothing, a rerun changes nothing, a different grant is not
  overwritten unless asked, and a revoke takes every reader back to "no grant";
- without the teacher switch, the teacher's profile is not touched.
"""

from __future__ import annotations

import importlib.util
import sys
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from fakes.dynamodb import FakeTable
from fakes.links import LinkRows
from stoa import config
from stoa.db import table as db_table
from stoa.db.repositories import (
    allowance_repo,
    identity_repo,
    user_repo,
)
from stoa.models.billing import BillingPlanId
from stoa.services import (
    allowance_service,
    entitlement_service,
    paid_entitlement_service,
    teacher_support_allowance_service as support,
)


def _load():
    path = Path(__file__).resolve().parents[1] / "scripts" / "grant_test_account_paid_access.py"
    spec = importlib.util.spec_from_file_location("grant_test_account_paid_access", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


tool = _load()

PARENT = "parent_6b79f6b551a7403dbc3a9474"
STUDENT = "student_a4e37a64453847fc9108ea35"
TEACHER = "teacher_9be74a537a1e43b3b837c0ce"
NOW = datetime(2026, 11, 18, 9, 0, tzinfo=timezone.utc)
ISSUER = "https://cognito-idp.eu-central-2.amazonaws.com/eu-central-2_Ss93YQzjJ"
SUBJECTS = {
    "parent@test.stoaedu.ch": ["sub-parent"],
    "student@test.stoaedu.ch": ["sub-student"],
    "teacher@test.stoaedu.ch": ["sub-teacher"],
}
BINDINGS = {"sub-parent": PARENT, "sub-student": STUDENT, "sub-teacher": TEACHER}


class FakeDirectory:
    issuer = ISSUER

    def __init__(self, subjects: dict[str, list[str]] | None = None) -> None:
        self.subjects = SUBJECTS if subjects is None else subjects

    def subjects_for_email(self, email: str) -> list[str]:
        return list(self.subjects.get(email, []))


def _profile(user_id: str, role: str, number: str, email: str, **extra: Any) -> dict[str, Any]:
    return {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "user_id": user_id,
        "role": role,
        "account_status": "active",
        "account_number": number,
        "email": email,
        "subscription_tier": "free_trial",
        "version": 7,
        **extra,
    }


@pytest.fixture
def accounts(fake_table: FakeTable) -> LinkRows:
    """The three shared test accounts, as the app stores them, and a current link."""
    fake_table.seed(
        _profile(PARENT, "parent", "P26-0001", "parent@test.stoaedu.ch"),
        _profile(STUDENT, "student", "S26-0001", "student@test.stoaedu.ch"),
        _profile(
            TEACHER,
            "teacher",
            "T26-0001",
            "teacher@test.stoaedu.ch",
            availability_status="unavailable",
            dispatch_active_count=2,
            primary_subjects=["chemistry"],
        ),
    )
    for user_id, number, role in (
        (PARENT, "P26-0001", "parent"),
        (STUDENT, "S26-0001", "student"),
        (TEACHER, "T26-0001", "teacher"),
    ):
        fake_table.seed_active_account(user_id, generation=3)
        fake_table.seed(
            {
                "PK": f"ACCOUNT_NUMBER#{number}",
                "SK": "ACCOUNT_NUMBER",
                "entity_type": "account_number",
                "account_number": number,
                "role": role,
                "account_id": user_id,
            }
        )
    for subject, user_id in BINDINGS.items():
        fake_table.seed(
            {
                "PK": f"IDENTITY#{identity_repo.issuer_hash(ISSUER)}#{subject}",
                "SK": "BINDING",
                "entity_type": "identity_binding",
                "issuer": ISSUER,
                "subject": subject,
                "user_id": user_id,
                "status": "active",
                "version": 1,
            }
        )
    rows = LinkRows(fake_table)
    rows.link(PARENT, STUDENT)
    return rows


def _run(*argv: str, directory: FakeDirectory | None = None):
    return tool.run(
        tool.parse_args(list(argv)),
        directory=directory or FakeDirectory(),
        now=lambda: NOW,
    )


def _grant_row(table: FakeTable) -> dict[str, Any] | None:
    return table.rows.get((f"PAID_GRANT#{PARENT}", f"BENEFICIARY#{STUDENT}"))


def _snapshot(table: FakeTable) -> dict[Any, Any]:
    return deepcopy(table.rows)


# -- what the app's readers make of the grant --------------------------------------------


def _entitlement() -> dict[str, Any]:
    return entitlement_service.resolve_student_entitlement(
        STUDENT, settings=config.settings(), now=NOW
    )


def _reserve(plan: str, output_tokens: int, effect: str):
    return allowance_service.reserve_token_allowance(
        beneficiary_id=STUDENT,
        effect_id=effect,
        plan_id=plan,
        allowance_version=1,
        input_tokens=1_000,
        max_output_tokens=output_tokens,
        observed_at=NOW,
        account_fence_generation=3,
    )


def _admit(case_id: str):
    table = db_table.table()

    def persist(operations, fences) -> bool:
        case = {
            "Put": {
                "Item": {"PK": f"QUESTION#{case_id}", "SK": "CASE", "case_id": case_id},
                "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
            }
        }
        try:
            db_table.fenced(STUDENT, [*operations, case], also=fences, table=table)
        except Exception:  # noqa: BLE001 - any refusal means the case was not written
            return False
        return True

    return support.admit_teacher_support_case(
        support_case_id=case_id,
        case_kind="question",
        beneficiary_id=STUDENT,
        persist_case=persist,
        observed_at=NOW,
        table=table,
    )


def _assert_paid(plan: BillingPlanId) -> None:
    grant = paid_entitlement_service.get_active_beneficiary_grant(PARENT, STUDENT)
    assert grant is not None and grant["plan_id"] == plan.value

    entitlement = _entitlement()
    assert entitlement["effectivePlan"] == plan.value
    assert entitlement["source"] == "paid_beneficiary_grant"
    assert entitlement["parentId"] == PARENT

    # 150k output tokens is fifteen times the free trial's week and inside this plan's.
    budget = allowance_service.plan_allowance_budget(plan, allowance_version=1)
    reserved = _reserve(entitlement["effectivePlan"], 150_000, f"effect-{plan.value}")
    assert reserved.disposition is allowance_repo.ReservationDisposition.ADMITTED
    # ...and the week's ceiling is this plan's 200k: 60k more would cross it.
    assert budget.output_tokens == 200_000
    over = _reserve(entitlement["effectivePlan"], 60_000, f"effect-{plan.value}-over")
    assert over.disposition is allowance_repo.ReservationDisposition.LIMIT_EXCEEDED

    admitted = _admit(f"case-{plan.value}")
    assert admitted.disposition is support.TeacherSupportAdmissionDisposition.ADMITTED
    assert admitted.admission is not None
    assert admitted.admission.plan_id is plan
    assert admitted.admission.limit == budget.teacher_support_cases


def _assert_unpaid(effect: str) -> None:
    assert paid_entitlement_service.get_active_beneficiary_grant(PARENT, STUDENT) is None

    entitlement = _entitlement()
    assert entitlement["effectivePlan"] == "free_trial"
    assert entitlement["source"] == "free_tier"

    refused = _reserve(entitlement["effectivePlan"], 150_000, effect)
    assert refused.disposition is allowance_repo.ReservationDisposition.LIMIT_EXCEEDED

    student = support._active_student(STUDENT)
    assert support._resolve_paid_scope(STUDENT, student, table=db_table.table()) is None
    # What is left is the figure every student is assigned, which is not a purchase.
    admitted = _admit(f"case-{effect}")
    assert admitted.admission is not None
    assert admitted.admission.plan_id is BillingPlanId.FREE_TRIAL


# -- the grant ---------------------------------------------------------------------------


def test_the_grant_it_writes_is_accepted_by_every_reader(fake_table, accounts) -> None:
    _assert_unpaid("before")

    report = _run("grant", "--parent", "P26-0001", "--student", "S26-0001", "--apply")

    assert report.wrote == [f"PAID_GRANT#{PARENT}/BENEFICIARY#{STUDENT}"]
    grant = _grant_row(fake_table)
    assert grant is not None
    assert grant["command_id"].startswith(tool.COMMAND_PREFIX)
    assert grant["relationship_source"] == paid_entitlement_service.RELATIONSHIP_SOURCE_LINK
    assert grant["student_profile_version"] == Decimal(7)
    _assert_paid(BillingPlanId.TEACHER_SUPPORTED)


def test_family_is_still_a_choice(fake_table, accounts) -> None:
    _run("--parent", PARENT, "--student", STUDENT, "--plan", "family", "--apply")

    _assert_paid(BillingPlanId.FAMILY)


def test_accounts_are_found_by_email_through_the_identity_binding(fake_table, accounts) -> None:
    report = _run(
        "--parent", "Parent@Test.StoaEdu.ch", "--student", "student@test.stoaedu.ch", "--apply"
    )

    assert report.wrote
    assert any("subject sub-parent -> binding" in line for line in report.lines)
    assert _grant_row(fake_table) is not None


def test_an_address_two_sign_in_identities_share_is_refused(fake_table, accounts) -> None:
    directory = FakeDirectory({**SUBJECTS, "parent@test.stoaedu.ch": ["sub-parent", "sub-x"]})

    with pytest.raises(tool.ToolError, match="2 sign-in identities"):
        _run("--parent", "parent@test.stoaedu.ch", "--student", "S26-0001", directory=directory)


def test_an_address_with_no_sign_in_identity_is_refused(fake_table, accounts) -> None:
    with pytest.raises(tool.ToolError, match="0 sign-in identities"):
        _run("--parent", "nobody@test.stoaedu.ch", "--student", "S26-0001")


def test_a_subject_without_a_binding_is_refused(fake_table, accounts) -> None:
    directory = FakeDirectory({**SUBJECTS, "parent@test.stoaedu.ch": ["sub-unbound"]})

    with pytest.raises(tool.ToolError, match="no active identity binding"):
        _run("--parent", "parent@test.stoaedu.ch", "--student", "S26-0001", directory=directory)


def test_an_unknown_account_number_is_refused(fake_table, accounts) -> None:
    with pytest.raises(tool.ToolError, match="no account holds this number"):
        _run("--parent", "P26-0099", "--student", "S26-0001")


# -- each precondition, on its own -------------------------------------------------------


def _refused(fake_table: FakeTable, match: str) -> None:
    before = _snapshot(fake_table)
    with pytest.raises(tool.ToolError, match=match):
        _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")
    assert fake_table.rows == before
    assert _grant_row(fake_table) is None


def test_no_link_is_refused(fake_table, accounts) -> None:
    accounts.unlink(PARENT, STUDENT)

    _refused(fake_table, "link parent side exists")


def test_a_link_with_only_one_side_is_refused(fake_table, accounts) -> None:
    accounts.unlink(PARENT, STUDENT)
    accounts.link(PARENT, STUDENT, only_parent_side=True)

    _refused(fake_table, r"\[FAIL\] link student side exists")


@pytest.mark.parametrize("status", ["pending", "rejected", "revoked"])
def test_a_link_that_is_not_active_is_refused(fake_table, accounts, status) -> None:
    accounts.set_status(PARENT, STUDENT, status)

    _refused(fake_table, rf"\[FAIL\] link parent side is active \(it is '{status}'\)")


def test_a_link_that_is_not_a_child_link_is_refused(fake_table, accounts) -> None:
    accounts.unlink(PARENT, STUDENT)
    accounts.link(PARENT, STUDENT, relationship="guardian")

    _refused(fake_table, r"\[FAIL\] link parent side is a child link")


@pytest.mark.parametrize("who", [PARENT, STUDENT])
def test_an_account_that_is_not_active_is_refused(fake_table, accounts, who) -> None:
    fake_table.rows[(f"USER#{who}", "PROFILE")]["account_status"] = "suspended"

    _refused(fake_table, "'suspended', not active")


def test_a_deleting_account_is_refused(fake_table, accounts) -> None:
    fake_table.rows[(f"USER#{STUDENT}", "ACCOUNT_FENCE")]["status"] = "deleting"

    _refused(fake_table, r"\[FAIL\] student .* account fence is active")


def test_the_wrong_role_is_refused(fake_table, accounts) -> None:
    before = _snapshot(fake_table)
    with pytest.raises(tool.ToolError, match="is a 'student', not a parent"):
        _run("--parent", "S26-0001", "--student", "S26-0001", "--apply")
    with pytest.raises(tool.ToolError, match="is a 'teacher', not a student"):
        _run("--parent", "P26-0001", "--student", TEACHER, "--apply")
    assert fake_table.rows == before


# -- dry run, rerun, replace -------------------------------------------------------------


def test_a_dry_run_writes_nothing_and_shows_every_row(fake_table, accounts) -> None:
    before = _snapshot(fake_table)

    report = _run(
        "--parent", "P26-0001", "--student", "S26-0001",
        "--complete-student-profile", "--set-subscription-tier", "teacher_supported",
        "--teacher", "T26-0001", "--set-teacher-dispatch", "available",
    )

    assert fake_table.rows == before
    assert report.wrote == []
    text = "\n".join(report.lines)
    assert "dry run: nothing written" in text
    assert f"PAID_GRANT#{PARENT}/BENEFICIARY#{STUDENT}" in text
    assert '"plan_id": "teacher_supported"' in text
    assert f"USER#{TEACHER}/PROFILE teacher dispatch" in text
    assert "[FAIL]" not in text


def test_running_it_again_changes_nothing(fake_table, accounts) -> None:
    _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")
    before = _snapshot(fake_table)

    report = _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")

    assert fake_table.rows == before
    assert report.wrote == []
    assert any("identical; nothing to do" in line for line in report.lines)


def test_a_different_grant_is_not_overwritten_unless_asked(fake_table, accounts) -> None:
    _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")
    before = _snapshot(fake_table)

    with pytest.raises(tool.ToolError) as refusal:
        _run("--parent", "P26-0001", "--student", "S26-0001", "--plan", "family", "--apply")

    assert "plan_id: 'teacher_supported' -> 'family'" in refusal.value.message
    assert "--replace" in refusal.value.message
    assert fake_table.rows == before

    _run("--parent", "P26-0001", "--student", "S26-0001", "--plan", "family", "--replace", "--apply")

    grant = _grant_row(fake_table)
    assert grant["plan_id"] == "family" and grant["grant_version"] == 2
    kept = fake_table.rows[(f"PAID_GRANT_HISTORY#{PARENT}", f"BENEFICIARY#{STUDENT}#VERSION#1")]
    assert kept["plan_id"] == "teacher_supported"


def test_a_purchase_is_never_revoked(fake_table, accounts) -> None:
    _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")
    fake_table.rows[(f"PAID_GRANT#{PARENT}", f"BENEFICIARY#{STUDENT}")]["command_id"] = "cmd-paid"
    before = _snapshot(fake_table)

    with pytest.raises(tool.ToolError, match="it is a purchase"):
        _run("revoke", "--parent", "P26-0001", "--student", "S26-0001", "--apply")
    assert fake_table.rows == before


def test_the_write_still_holds_the_link_when_it_changes_after_the_read(
    fake_table, accounts, monkeypatch
) -> None:
    """The grant goes in behind the link rows, not behind what was read of them."""
    real = db_table.fenced

    def revoke_first(*args, **kwargs):
        accounts.set_status(PARENT, STUDENT, "revoked")
        return real(*args, **kwargs)

    monkeypatch.setattr(db_table, "fenced", revoke_first)

    with pytest.raises(tool.ToolError, match="the table refused the write"):
        _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")
    assert _grant_row(fake_table) is None


# -- revoke ------------------------------------------------------------------------------


def test_revoke_takes_every_reader_back_to_no_grant(fake_table, accounts) -> None:
    _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")
    _assert_paid(BillingPlanId.TEACHER_SUPPORTED)
    before = _snapshot(fake_table)

    dry = _run("revoke", "--parent", "P26-0001", "--student", "S26-0001")
    assert fake_table.rows == before
    assert any("grant_status: 'active' -> 'historical'" in line for line in dry.lines)

    _run("revoke", "--parent", "P26-0001", "--student", "S26-0001", "--apply")

    assert _grant_row(fake_table)["grant_status"] == "historical"
    assert (f"PAID_GRANT_HISTORY#{PARENT}", f"BENEFICIARY#{STUDENT}#VERSION#1") in fake_table.rows
    _assert_unpaid("after-revoke")

    again = _run("revoke", "--parent", "P26-0001", "--student", "S26-0001", "--apply")
    assert again.wrote == []


def test_a_revoked_grant_can_be_given_again(fake_table, accounts) -> None:
    _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")
    _run("revoke", "--parent", "P26-0001", "--student", "S26-0001", "--apply")

    _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")

    grant = _grant_row(fake_table)
    assert grant["grant_status"] == "active" and grant["grant_version"] == 2
    _assert_paid(BillingPlanId.TEACHER_SUPPORTED)


# -- the switches ------------------------------------------------------------------------


def test_without_the_switch_the_teacher_is_not_touched(fake_table, accounts) -> None:
    teacher = deepcopy(fake_table.rows[(f"USER#{TEACHER}", "PROFILE")])

    _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")
    _run("revoke", "--parent", "P26-0001", "--student", "S26-0001", "--apply")

    assert fake_table.rows[(f"USER#{TEACHER}", "PROFILE")] == teacher
    for user_id in (PARENT, STUDENT):
        profile = fake_table.rows[(f"USER#{user_id}", "PROFILE")]
        assert profile["subscription_tier"] == "free_trial"
        assert profile["version"] == Decimal(7)


def test_the_switches_go_through_the_profile_writer_before_the_grant(fake_table, accounts) -> None:
    _run(
        "--parent", "P26-0001", "--student", "S26-0001", "--apply",
        "--complete-student-profile",
        "--teacher", "T26-0001", "--set-teacher-dispatch", "available",
    )

    student = fake_table.rows[(f"USER#{STUDENT}", "PROFILE")]
    assert student["primary_subjects"] == ["mathematics"]
    # The grant records the version the subject write left, so admission still holds.
    assert _grant_row(fake_table)["student_profile_version"] == student["version"] == Decimal(8)
    teacher = fake_table.rows[(f"USER#{TEACHER}", "PROFILE")]
    assert teacher["availability_status"] == "available"
    assert teacher["dispatch_active_count"] == Decimal(2)  # a live counter is not reset
    _assert_paid(BillingPlanId.TEACHER_SUPPORTED)

    _run(
        "revoke", "--parent", "P26-0001", "--student", "S26-0001", "--apply",
        "--teacher", "T26-0001", "--set-teacher-dispatch", "unavailable",
    )
    assert fake_table.rows[(f"USER#{TEACHER}", "PROFILE")]["availability_status"] == "unavailable"


def test_the_teacher_switch_says_what_it_does_in_production() -> None:
    text = _help()
    assert "PRODUCTION EFFECT" in text
    assert "real students' teacher-help requests" in text


def _help() -> str:
    import contextlib
    import io

    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit):
        tool.parse_args(["--help"])
    return " ".join(out.getvalue().split())


# -- the app behaviour the PR reports ----------------------------------------------------


def test_a_sign_in_after_the_grant_stops_paid_teacher_help_until_it_is_restamped(
    fake_table, accounts
) -> None:
    """Teacher-help admission fences the profile versions the grant recorded.

    Every password sign-in moves `version` (`user_repo.record_sign_in`), so after
    the student signs in the paid scope is still resolved but its transaction is
    refused, four times, and the admission answers `retryable_dependency`. Not the
    tool's to fix; `--replace` re-stamps the grant with the current versions.
    """
    _run("--parent", "P26-0001", "--student", "S26-0001", "--apply")
    profile = user_repo.get_user(STUDENT)
    user_repo.record_sign_in(STUDENT, profile, signed_in_at=NOW.isoformat())

    stale = _admit("case-after-sign-in")
    assert stale.disposition is support.TeacherSupportAdmissionDisposition.RETRYABLE

    _run("--parent", "P26-0001", "--student", "S26-0001", "--replace", "--apply")
    _assert_paid(BillingPlanId.TEACHER_SUPPORTED)

