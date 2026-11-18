#!/usr/bin/env python3
"""Give a linked test student paid access through their parent, the way the app would.

An operator tool for the shared test accounts. Payments are frozen, so no
provider activation can write a `PAID_GRANT#{parent}/BENEFICIARY#{student}` row
for them; this writes that one row and nothing else, unless told to.

What it does, by default, is nothing: every action is a dry run that reads the
accounts, checks every precondition and prints the exact rows it would write.
`--apply` writes them.

    grant   (default) build the grant with the app's own builder
            (`paid_entitlement_service.build_paid_activation_operations`) and
            commit it behind the same condition checks and account fences the
            provider activation commits it behind (`db_table.fenced`).
    revoke  end a grant this tool wrote, the way the app ends a grant
            (`apply_due_paid_transition`): the row stays, `grant_status` becomes
            `historical`, and a `PAID_GRANT_HISTORY#` row keeps what it was.
            Readers then answer exactly as if there had never been a grant.

Accounts are named by email (resolved through Cognito and the identity binding
the request path uses), by account number (`S26-0001`) or by user id.

Separate switches, each off unless given, for the side changes the old
`enable_teacher_support_testing.py` made unconditionally:

    --complete-student-profile     give the student the subjects registration writes
    --set-subscription-tier TIER   set `subscription_tier` on both profiles
    --teacher T --set-teacher-dispatch available|unavailable

Profile writes go first, through the versioned profile writer, so the grant is
stamped with the profile versions they leave behind.

Usage (PowerShell, from the repository root):

    $env:AWS_PROFILE = "AdministratorAccess-562923011260"
    & "D:\\STOA backend\\.venv\\Scripts\\python.exe" scripts\\grant_test_account_paid_access.py `
        grant --parent P26-0001 --student S26-0001             # dry run
    ... the same line with --apply                             # write
    ... revoke --parent P26-0001 --student S26-0001 [--apply]  # undo
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Protocol

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

# Import order matters. `paid_entitlement_service` cannot be the first of the
# billing services a process imports: through attachment_service -> uploads ->
# moderation_service -> help_requests it reaches teacher_support_allowance_service,
# whose class body reads `paid_entitlement_service.RELATIONSHIP_SOURCE_LINK` while
# that module is still half-imported. The Lambda entry (`stoa.main`) reaches these
# modules through `entitlement_service` first, so every cold start imports them in
# that order; this does the same. Not `stoa.main` itself: it builds the settings at
# import, before `main` can point them at --region/--table.
# tests/test_grant_test_account_paid_access.py starts this file in fresh
# interpreters to keep it importable.
import stoa.services.entitlement_service  # noqa: E402, F401  (must come first; see above)
from stoa.db import table as db_table  # noqa: E402
from stoa.db.repositories import (  # noqa: E402
    account_deletion_repo,
    account_number_repo,
    billing_fact_repo,
    identity_repo,
    parent_link_repo,
    user_repo,
)
from stoa.models.billing import BillingPlanId  # noqa: E402
from stoa.services import (  # noqa: E402
    account_numbering_service,
    current_relationship,
    paid_entitlement_service,
)

REGION = "eu-central-2"
TABLE_NAME = "stoa-main"
USER_POOL_ID = "eu-central-2_Ss93YQzjJ"

# `teacher_supported` is the default: `family` is expected to be withdrawn (#482).
DEFAULT_PLAN = BillingPlanId.TEACHER_SUPPORTED
PLAN_CHOICES = (BillingPlanId.TEACHER_SUPPORTED.value, BillingPlanId.FAMILY.value)
TIER_CHOICES = tuple(plan.value for plan in BillingPlanId)
STUDENT_SUBJECTS = ["mathematics"]
TEACHER_SUBJECTS = ["mathematics", "physics"]

# Every grant this tool writes carries this command id prefix. `revoke` refuses
# any other grant: one the provider wrote is a purchase, not a test fixture.
COMMAND_PREFIX = "manual-test-"
# Stamped on the request the builder takes and on nothing it stores: these
# fields describe a provider payment there was none of.
NO_PROVIDER = "manual-test-no-provider"
# Fields that change on every run without changing what the grant grants.
_RUN_FIELDS = frozenset({"activated_at", "grant_version", "activation_version"})


class ToolError(SystemExit):
    """A refusal: printed, and the process exits 1 without writing."""

    def __init__(self, message: str) -> None:
        super().__init__(1)
        self.message = message

    def __str__(self) -> str:
        return self.message


# -- finding the accounts ---------------------------------------------------------------


class Directory(Protocol):
    """The sign-in directory: who an address is, as the request path will see it."""

    issuer: str

    def subjects_for_email(self, email: str) -> list[str]: ...


class CognitoDirectory:
    def __init__(self, client: Any, *, region: str, user_pool_id: str) -> None:
        self._client = client
        self._pool = user_pool_id
        self.issuer = f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"

    def subjects_for_email(self, email: str) -> list[str]:
        subjects: list[str] = []
        token: str | None = None
        while True:
            request: dict[str, Any] = {
                "UserPoolId": self._pool,
                "Filter": f'email = "{email}"',
            }
            if token:
                request["PaginationToken"] = token
            response = self._client.list_users(**request)
            for user in response.get("Users", []):
                for attribute in user.get("Attributes", []):
                    if attribute.get("Name") == "sub":
                        subjects.append(str(attribute["Value"]))
            token = response.get("PaginationToken")
            if not token:
                return subjects


@dataclass(frozen=True)
class Account:
    user_id: str
    role: str
    profile: dict[str, Any]
    found_by: str


def _plain(value: Any) -> Any:
    """Stored numbers come back as Decimal; print and compare them as ints."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, Mapping):
        return {key: _plain(member) for key, member in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(member) for member in value]
    return value


def _user_id_for(reference: str, *, role: str, directory: Directory | None) -> tuple[str, str]:
    text = reference.strip()
    if "@" in text:
        if directory is None:
            raise ToolError(f"{text}: an email needs the sign-in directory")
        email = text.casefold()
        subjects = directory.subjects_for_email(email)
        if len(subjects) != 1:
            raise ToolError(
                f"{text}: {len(subjects)} sign-in identities carry this address; "
                "name the account by its number or user id instead"
            )
        binding = identity_repo.get_identity_binding(directory.issuer, subjects[0])
        if not binding or binding.get("status") != "active" or not binding.get("user_id"):
            raise ToolError(
                f"{text}: sign-in subject {subjects[0]} has no active identity binding, "
                "so the app would refuse this sign-in"
            )
        return str(binding["user_id"]), f"email {email} -> subject {subjects[0]} -> binding"
    if account_numbering_service.ACCOUNT_NUMBER_PATTERN.match(text):
        claim = account_number_repo.get_account_number_claim(text)
        if not claim or not claim.get("account_id"):
            raise ToolError(f"{text}: no account holds this number")
        return str(claim["account_id"]), f"account number {text}"
    if not text:
        raise ToolError(f"no {role} given")
    return text, "user id"


def resolve_account(
    reference: str, *, role: str, directory: Directory | None
) -> Account:
    """The one account `reference` names, refused unless it is an active `role`."""
    user_id, found_by = _user_id_for(reference, role=role, directory=directory)
    profile = user_repo.get_user(user_id)
    if not profile:
        raise ToolError(f"{reference}: {user_id} has no profile")
    profile = dict(profile)
    if profile.get("user_id") != user_id:
        raise ToolError(f"{reference}: profile user_id does not match {user_id}")
    if profile.get("role") != role:
        raise ToolError(f"{reference}: {user_id} is a {profile.get('role')!r}, not a {role}")
    if profile.get("account_status") != "active":
        raise ToolError(
            f"{reference}: {user_id} is {profile.get('account_status')!r}, not active"
        )
    number = profile.get("account_number")
    if (
        account_numbering_service.ACCOUNT_NUMBER_PATTERN.match(reference.strip())
        and number
        and number != reference.strip()
    ):
        raise ToolError(f"{reference}: {user_id} carries account number {number}")
    if "@" in reference and profile.get("email"):
        if str(profile["email"]).casefold() != reference.strip().casefold():
            raise ToolError(f"{reference}: {user_id} carries address {profile['email']}")
    return Account(user_id=user_id, role=role, profile=profile, found_by=found_by)


# -- preconditions ---------------------------------------------------------------------


@dataclass
class Checks:
    results: list[tuple[bool, str]] = field(default_factory=list)

    def add(self, ok: bool, label: str) -> bool:
        self.results.append((bool(ok), label))
        return bool(ok)

    @property
    def passed(self) -> bool:
        return all(ok for ok, _ in self.results)

    def lines(self) -> list[str]:
        return [f"  [{'ok' if ok else 'FAIL'}] {label}" for ok, label in self.results]


def _positive(value: Any) -> bool:
    try:
        return not isinstance(value, bool) and int(value) > 0 and int(value) == value
    except (TypeError, ValueError):
        return False


def relationship_checks(parent: Account, student: Account) -> Checks:
    """Every condition the grant's readers and its writer ask of the pair, one by one."""
    checks = Checks()
    for account in (parent, student):
        label = f"{account.role} {account.user_id}"
        checks.add(_positive(account.profile.get("version")), f"{label}: profile has a version")
        fence = account_deletion_repo.get_account_fence(account.user_id)
        checks.add(
            bool(fence)
            and fence.get("status") == "active"
            and _positive(fence.get("generation")),
            f"{label}: account fence is active",
        )
    sides = (
        ("parent side", parent_link_repo.get_parent_side_link(parent.user_id, student.user_id)),
        ("student side", parent_link_repo.get_student_side_link(student.user_id, parent.user_id)),
    )
    for name, row in sides:
        present = checks.add(row is not None, f"link {name} exists")
        if not present:
            continue
        assert row is not None
        checks.add(
            row.get("entity_type") == parent_link_repo.ENTITY_TYPE
            and row.get("parent_id") == parent.user_id
            and row.get("student_id") == student.user_id,
            f"link {name} names this pair",
        )
        checks.add(
            row.get("status") == parent_link_repo.STATUS_ACTIVE,
            f"link {name} is active (it is {row.get('status')!r})",
        )
        checks.add(
            row.get("relationship") == paid_entitlement_service.BENEFICIARY_RELATIONSHIP,
            f"link {name} is a child link (it is {row.get('relationship')!r})",
        )
    verdict = current_relationship.judge(parent.user_id, student.user_id)
    checks.add(
        paid_entitlement_service.relationship_authority(parent.user_id, student.user_id)
        is not None,
        f"the relationship judge holds the pair current (it says {verdict.standing.value})",
    )
    return checks


# -- the grant --------------------------------------------------------------------------


def subscription_digest(parent_id: str, student_id: str) -> str:
    """The stand-in for a provider subscription id: fixed per pair, so reruns agree.

    The derivation is the one `enable_teacher_support_testing.py` used, so a grant
    it wrote is recognised as this tool's own.
    """
    return hashlib.sha256(
        f"stoa:manual-test-entitlement:v1:{parent_id}:{student_id}".encode()
    ).hexdigest()


def grant_key(parent_id: str, student_id: str) -> dict[str, str]:
    return {"PK": f"PAID_GRANT#{parent_id}", "SK": f"BENEFICIARY#{student_id}"}


def stored_grant(parent_id: str, student_id: str) -> dict[str, Any] | None:
    item = db_table.get(Key=grant_key(parent_id, student_id), ConsistentRead=True)
    return dict(item) if item else None


def build_grant(
    parent: Account,
    student: Account,
    *,
    plan: BillingPlanId,
    version: int,
    now: datetime,
) -> paid_entitlement_service.PaidGrantBuild:
    """The grant and its conditions, from the app's own activation builder.

    The builder reads the profiles, the link rows and both account fences
    itself (`_relationship_proof`) and stamps what it read on the grant, which
    the teacher-support admission later re-asserts. Only the fields it reads off
    the request matter; the provider fields are placeholders it never stores.
    """
    digest = subscription_digest(parent.user_id, student.user_id)
    command_id = f"{COMMAND_PREFIX}{digest[:16]}"
    request = billing_fact_repo.PaidActivationRequest(
        command_id=command_id,
        parent_id=parent.user_id,
        expected_command_version=1,
        provider_customer_id_digest=digest,
        price_id=NO_PROVIDER,
        environment=NO_PROVIDER,
        plan_id=plan,
        plan_version=1,
        allowance_version=1,
        activation_version=version,
        paid_invoice_fact_id=NO_PROVIDER,
        active_subscription_fact_id=NO_PROVIDER,
        activated_at=now.isoformat(),
        provider_subscription_id_digest=digest,
    )
    command = {
        "command_id": command_id,
        "parent_id": parent.user_id,
        "plan_id": str(plan),
        "plan_version": 1,
        "provider_subscription_id_digest": digest,
        "beneficiary_ids": [student.user_id],
    }
    return paid_entitlement_service.build_paid_activation_operations(request, command=command)


def history_operation(grant: Mapping[str, Any], *, reason: str, now: datetime) -> dict[str, Any] | None:
    """Keep what a grant was before it is ended or replaced, as a transition does."""
    item = paid_entitlement_service._grant_history_item(  # noqa: SLF001 - the app's own row
        grant,
        {
            "transition_identity": hashlib.sha256(
                f"stoa:manual-test-transition:v1\n{reason}\n{now.isoformat()}".encode()
            ).hexdigest(),
            "effective_at": now.isoformat(),
        },
    )
    if db_table.get(Key={"PK": item["PK"], "SK": item["SK"]}, ConsistentRead=True):
        return None  # already kept
    return {
        "Put": {
            "Item": item,
            "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)",
        }
    }


def _replace_condition(existing: Mapping[str, Any]) -> dict[str, Any]:
    """Overwrite exactly the row that was read, or nothing."""
    return {
        "ConditionExpression": (
            "grant_status=:status AND grant_version=:grant_version "
            "AND subscription_id_digest=:digest"
        ),
        "ExpressionAttributeValues": {
            ":status": existing.get("grant_status"),
            ":grant_version": existing.get("grant_version"),
            ":digest": existing.get("subscription_id_digest"),
        },
    }


def diff(old: Mapping[str, Any], new: Mapping[str, Any]) -> list[str]:
    lines = []
    for name in sorted(set(old) | set(new)):
        before, after = _plain(old.get(name)), _plain(new.get(name))
        if before != after:
            lines.append(f"    {name}: {before!r} -> {after!r}")
    return lines


def _same_grant(existing: Mapping[str, Any], built: Mapping[str, Any]) -> bool:
    return all(
        _plain(existing.get(name)) == _plain(built.get(name))
        for name in set(existing) | set(built)
        if name not in _RUN_FIELDS
    )


# -- the optional profile switches ------------------------------------------------------


@dataclass(frozen=True)
class ProfileChange:
    user_id: str
    label: str
    fields: dict[str, Any]


def profile_changes(
    parent: Account,
    student: Account,
    teacher: Account | None,
    *,
    complete_student_profile: bool,
    subscription_tier: str | None,
    teacher_dispatch: str | None,
) -> list[ProfileChange]:
    changes: list[ProfileChange] = []
    if complete_student_profile:
        missing = {
            name: list(STUDENT_SUBJECTS)
            for name in ("primary_subjects", "subjects")
            if not isinstance(student.profile.get(name), list)
        }
        if missing:
            changes.append(ProfileChange(student.user_id, "student subjects", missing))
    if subscription_tier is not None:
        for account in (parent, student):
            if account.profile.get("subscription_tier") != subscription_tier:
                changes.append(
                    ProfileChange(
                        account.user_id,
                        f"{account.role} subscription_tier",
                        {"subscription_tier": subscription_tier},
                    )
                )
    if teacher is not None and teacher_dispatch is not None:
        changes.append(
            ProfileChange(
                teacher.user_id,
                "teacher dispatch",
                {"availability_status": teacher_dispatch, "dispatch_availability": teacher_dispatch}
                | ({"subjects": TEACHER_SUBJECTS} if teacher_dispatch == "available" else {}),
            )
        )
    return changes


def apply_profile_change(change: ProfileChange, *, now: datetime) -> None:
    if change.label == "teacher dispatch":
        status = str(change.fields["availability_status"])
        user_repo.update_teacher_availability(
            change.user_id,
            subjects=TEACHER_SUBJECTS if status == "available" else None,
            weekly_availability=None,
            updated_at=now.isoformat(),
            status=status,
        )
        return
    values = {f":{name}": value for name, value in change.fields.items()}
    values[":updated_at"] = now.isoformat()
    user_repo.update_profile_fields(
        change.user_id,
        update_expression="SET "
        + ", ".join(f"{name} = :{name}" for name in change.fields)
        + ", updated_at = :updated_at",
        expression_attribute_values=values,
    )


# -- the two actions --------------------------------------------------------------------


@dataclass
class Report:
    lines: list[str] = field(default_factory=list)
    wrote: list[str] = field(default_factory=list)

    def say(self, line: str = "") -> None:
        self.lines.append(line)

    def row(self, label: str, item: Mapping[str, Any]) -> None:
        self.say(f"  {label}:")
        for line in json.dumps(_plain(item), indent=2, sort_keys=True).splitlines():
            self.say(f"    {line}")


def _describe(report: Report, *accounts: Account | None) -> None:
    for account in accounts:
        if account is None:
            continue
        profile = account.profile
        report.say(
            f"  {account.role:8} {account.user_id}  ({account.found_by}; "
            f"number={profile.get('account_number')}, status={profile.get('account_status')}, "
            f"version={_plain(profile.get('version'))}, "
            f"subscription_tier={profile.get('subscription_tier')})"
        )


def run_grant(
    parent: Account,
    student: Account,
    *,
    plan: BillingPlanId,
    apply: bool,
    replace: bool,
    now: datetime,
    teacher: Account | None = None,
    complete_student_profile: bool = False,
    subscription_tier: str | None = None,
    teacher_dispatch: str | None = None,
) -> Report:
    report = Report()
    report.say(f"grant {plan.value}: {'APPLY' if apply else 'dry run, nothing is written'}")
    _describe(report, parent, student, teacher)

    report.say("preconditions:")
    checks = relationship_checks(parent, student)
    report.lines.extend(checks.lines())
    if not checks.passed:
        raise ToolError("\n".join([*report.lines, "precondition failed; nothing written"]))

    changes = profile_changes(
        parent,
        student,
        teacher,
        complete_student_profile=complete_student_profile,
        subscription_tier=subscription_tier,
        teacher_dispatch=teacher_dispatch,
    )
    report.say("profile changes (only those switched on):")
    if not changes:
        report.say("  none")
    for change in changes:
        report.say(f"  USER#{change.user_id}/PROFILE {change.label}: {_plain(change.fields)}")
    if apply:
        for change in changes:
            apply_profile_change(change, now=now)
            report.wrote.append(f"USER#{change.user_id}/PROFILE ({change.label})")
        if changes:
            # The grant stamps the profile versions; read them as now written.
            parent = resolve_account(parent.user_id, role="parent", directory=None)
            student = resolve_account(student.user_id, role="student", directory=None)
    elif changes:
        report.say("  (each bumps that profile's version; the grant is built after them)")

    existing = stored_grant(parent.user_id, student.user_id)
    version = 1 if existing is None else int(_plain(existing.get("grant_version")) or 0) + 1
    try:
        built = build_grant(parent, student, plan=plan, version=version, now=now)
    except (paid_entitlement_service.PaidGrantConflict, ValueError) as exc:
        raise ToolError("\n".join([*report.lines, f"the app refuses the grant: {exc}"])) from exc
    grant = dict(built.grant_items[0])

    operations: list[dict[str, Any]] = list(built.grant_operations)
    if existing is None:
        put_condition: dict[str, Any] = {
            "ConditionExpression": "attribute_not_exists(PK) AND attribute_not_exists(SK)"
        }
        report.say("existing grant: none")
    elif existing.get("grant_status") == "active" and _same_grant(existing, grant):
        report.say("existing grant: active and identical; nothing to do")
        report.row(f"PAID_GRANT#{parent.user_id}/BENEFICIARY#{student.user_id}", existing)
        return report
    else:
        report.say(f"existing grant ({existing.get('grant_status')}) differs:")
        report.lines.extend(diff(existing, grant))
        ours = str(existing.get("command_id") or "").startswith(COMMAND_PREFIX)
        if existing.get("grant_status") == "active" and not replace:
            raise ToolError(
                "\n".join([*report.lines, "an active grant is already there; "
                           "pass --replace to overwrite it (its old values are kept "
                           "as a PAID_GRANT_HISTORY row)"])
            )
        if not ours and not replace:
            raise ToolError(
                "\n".join([*report.lines, "the grant there was not written by this tool; "
                           "pass --replace to overwrite it"])
            )
        put_condition = _replace_condition(existing)
        history = history_operation(existing, reason="replaced", now=now)
        if history is not None:
            operations.append(history)
            report.row("PAID_GRANT_HISTORY (kept copy of the row replaced)", history["Put"]["Item"])

    operations.append({"Put": {"Item": grant, **put_condition}})
    report.row(f"PAID_GRANT#{parent.user_id}/BENEFICIARY#{student.user_id}", grant)
    report.say(
        f"  written in one transaction behind {len(built.grant_operations)} condition checks "
        f"(both profiles at their versions, both link sides active) and the account fences "
        f"{_plain(built.account_fences)}; db_table.fenced adds the owner-registry row "
        f"USER#{student.user_id}/REFERENCED_IN#PAID_GRANT#{parent.user_id} (and one for "
        "any PAID_GRANT_HISTORY row) so account deletion finds them"
    )
    if not apply:
        report.say("dry run: nothing written. Add --apply to write.")
        return report
    _commit(parent.user_id, operations, built.account_fences)
    report.wrote.append(f"PAID_GRANT#{parent.user_id}/BENEFICIARY#{student.user_id}")
    report.say("written.")
    return report


def run_revoke(
    parent: Account,
    student: Account,
    *,
    apply: bool,
    now: datetime,
    teacher: Account | None = None,
    subscription_tier: str | None = None,
    teacher_dispatch: str | None = None,
) -> Report:
    report = Report()
    report.say(f"revoke: {'APPLY' if apply else 'dry run, nothing is written'}")
    _describe(report, parent, student, teacher)
    existing = stored_grant(parent.user_id, student.user_id)
    changes = profile_changes(
        parent,
        student,
        teacher,
        complete_student_profile=False,
        subscription_tier=subscription_tier,
        teacher_dispatch=teacher_dispatch,
    )
    report.say("profile changes (only those switched on):")
    if not changes:
        report.say("  none")
    for change in changes:
        report.say(f"  USER#{change.user_id}/PROFILE {change.label}: {_plain(change.fields)}")

    operations: list[dict[str, Any]] = []
    if existing is None or existing.get("grant_status") != "active":
        report.say(
            "existing grant: "
            + ("none" if existing is None else f"already {existing.get('grant_status')}")
            + "; nothing to revoke"
        )
    else:
        if not str(existing.get("command_id") or "").startswith(COMMAND_PREFIX):
            raise ToolError(
                "\n".join([*report.lines, "the active grant there was not written by this "
                           "tool (it is a purchase); refusing to end it"])
            )
        ended = {
            **existing,
            "grant_status": "historical",
            "ended_at": now.isoformat(),
            "ended_by_transition": f"{COMMAND_PREFIX}revoke",
            "transitioned_at": now.isoformat(),
        }
        history = history_operation(existing, reason="revoked", now=now)
        if history is not None:
            operations.append(history)
            report.row("PAID_GRANT_HISTORY (kept copy of the grant)", history["Put"]["Item"])
        operations.append({"Put": {"Item": ended, **_replace_condition(existing)}})
        report.say("grant change:")
        report.lines.extend(diff(existing, ended))

    if not apply:
        report.say("dry run: nothing written. Add --apply to write.")
        return report
    if operations:
        fences = {
            parent.user_id: None,
            student.user_id: None,
        }
        _commit(parent.user_id, operations, fences)
        report.wrote.append(f"PAID_GRANT#{parent.user_id}/BENEFICIARY#{student.user_id}")
    for change in changes:
        apply_profile_change(change, now=now)
        report.wrote.append(f"USER#{change.user_id}/PROFILE ({change.label})")
    report.say("written." if report.wrote else "nothing to write.")
    return report


def _commit(
    parent_id: str, operations: Sequence[dict[str, Any]], fences: Mapping[str, int | None]
) -> None:
    """One transaction behind the parent's fence and every other account's."""
    held = dict(fences)
    generation = held.pop(parent_id, None)
    try:
        db_table.fenced(parent_id, list(operations), generation=generation, also=held)
    except (db_table.WriteRefused, account_deletion_repo.AccountDeletionConflict) as exc:
        raise ToolError(
            "the table refused the write (a profile, link, fence or the grant changed "
            f"after it was read): {type(exc).__name__}; nothing was written"
        ) from exc


# -- command line -----------------------------------------------------------------------


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Grant or revoke paid access for a linked test student. "
        "Dry run unless --apply.",
    )
    parser.add_argument("action", nargs="?", choices=("grant", "revoke"), default="grant")
    parser.add_argument("--parent", required=True, help="email, account number (P26-0001) or user id")
    parser.add_argument("--student", required=True, help="email, account number (S26-0001) or user id")
    parser.add_argument("--plan", choices=PLAN_CHOICES, default=DEFAULT_PLAN.value)
    parser.add_argument("--apply", action="store_true", help="write; without it nothing is written")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="overwrite a grant that is already there and differs (the old one is kept "
        "as a PAID_GRANT_HISTORY row). Also how to re-stamp a grant after either account "
        "signed in: sign-in moves the profile version the grant recorded.",
    )
    parser.add_argument(
        "--complete-student-profile",
        action="store_true",
        help=f"grant only: set primary_subjects/subjects={STUDENT_SUBJECTS} on the student "
        "profile where missing",
    )
    parser.add_argument(
        "--set-subscription-tier",
        choices=TIER_CHOICES,
        help="set subscription_tier on both profiles. Note a paid tier on the student's own "
        "profile is paid access by itself (source student_profile) and revoke does not "
        "undo it unless given --set-subscription-tier free_trial",
    )
    parser.add_argument("--teacher", help="the teacher --set-teacher-dispatch acts on")
    parser.add_argument(
        "--set-teacher-dispatch",
        choices=("available", "unavailable"),
        help="PRODUCTION EFFECT: 'available' puts this teacher into live dispatch, so real "
        "students' teacher-help requests in these subjects can be routed to this test "
        "account and wait on nobody. Use only while someone is watching it, and set "
        "'unavailable' afterwards.",
    )
    parser.add_argument("--table", default=TABLE_NAME)
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--user-pool-id", default=USER_POOL_ID)
    args = parser.parse_args(argv)
    if args.set_teacher_dispatch and not args.teacher:
        parser.error("--set-teacher-dispatch needs --teacher")
    if args.teacher and not args.set_teacher_dispatch:
        parser.error("--teacher is only used with --set-teacher-dispatch")
    if args.action == "revoke" and (args.complete_student_profile or args.replace):
        parser.error("--complete-student-profile and --replace are grant options")
    return args


def run(
    args: argparse.Namespace,
    *,
    directory: Directory | None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc).replace(microsecond=0),
) -> Report:
    parent = resolve_account(args.parent, role="parent", directory=directory)
    student = resolve_account(args.student, role="student", directory=directory)
    teacher = (
        resolve_account(args.teacher, role="teacher", directory=directory)
        if args.teacher
        else None
    )
    if args.action == "revoke":
        return run_revoke(
            parent,
            student,
            apply=args.apply,
            now=now(),
            teacher=teacher,
            subscription_tier=args.set_subscription_tier,
            teacher_dispatch=args.set_teacher_dispatch,
        )
    return run_grant(
        parent,
        student,
        plan=BillingPlanId(args.plan),
        apply=args.apply,
        replace=args.replace,
        now=now(),
        teacher=teacher,
        complete_student_profile=args.complete_student_profile,
        subscription_tier=args.set_subscription_tier,
        teacher_dispatch=args.set_teacher_dispatch,
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    # The gateway sends transactions through a client built from the app's
    # settings; these win over any `.env`, so both point at the same table.
    os.environ["AWS_REGION"] = args.region
    os.environ["DYNAMODB_TABLE_NAME"] = args.table
    import boto3

    db_table.install(boto3.resource("dynamodb", region_name=args.region).Table(args.table))
    directory = CognitoDirectory(
        boto3.client("cognito-idp", region_name=args.region),
        region=args.region,
        user_pool_id=args.user_pool_id,
    )
    print(f"table={args.table} region={args.region} pool={args.user_pool_id}")
    try:
        report = run(args, directory=directory)
    except ToolError as refusal:
        print(refusal.message)
        return 1
    print("\n".join(report.lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
