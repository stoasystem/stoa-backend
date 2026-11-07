"""#34 / #85 / #287: the admission fences the link rows the scope was resolved from.

The paid scope is resolved from a current link (`current_relationship.judge`),
read outside the admission transaction. The transaction asserts both link rows
itself, so a relationship closed between the read and the write refuses the
admission. These tests hold the transaction to that.
"""

from __future__ import annotations

from typing import Any

from stoa.models.allowance import TeacherSupportScope
from stoa.models.billing import BillingPlanId
from stoa.services import teacher_support_allowance_service as allowance

# Reached through the allowance module: importing `paid_entitlement_service`
# first closes an import cycle back through `teacher_support_allowance_service`.
paid_entitlement_service = allowance.paid_entitlement_service


def _scope(**overrides: Any) -> allowance._ResolvedScope:
    values: dict[str, Any] = {
        "beneficiary_id": "student-1",
        "parent_id": "parent-1",
        "plan_id": BillingPlanId.STUDENT,
        "plan_version": 1,
        "allowance_version": 1,
        "grant_version": 1,
        "subscription_id_digest": "d" * 64,
        "grant_id": "grant-1",
        "support_scope": TeacherSupportScope.PER_BENEFICIARY,
        "support_scope_id": "scope-1",
        "limit": 3,
        "grant": {
            "parent_account_fence_generation": 1,
            "student_account_fence_generation": 1,
            "parent_profile_version": 4,
            "student_profile_version": 5,
        },
    }
    values.update(overrides)
    return allowance._ResolvedScope(**values)


def _checks(scope: allowance._ResolvedScope) -> dict[tuple[str, str], dict[str, Any]]:
    checks: dict[tuple[str, str], dict[str, Any]] = {}
    for operation in allowance._grant_condition_operations(scope):
        body = operation.get("ConditionCheck")
        if body is not None:
            checks[(body["Key"]["PK"], body["Key"]["SK"])] = body
    return checks


def test_a_paid_admission_fences_both_link_rows_as_active_child_links() -> None:
    scope = _scope()
    assert scope.relationship_source == paid_entitlement_service.RELATIONSHIP_SOURCE_LINK
    checks = _checks(scope)
    forward = checks[("PARENT#parent-1", "CHILD#student-1")]
    reverse = checks[("STUDENT#student-1", "PARENT#parent-1")]
    for body in (forward, reverse):
        values = body["ExpressionAttributeValues"]
        assert values[":entity_type"] == "parent_student_link"
        assert values[":parent_id"] == "parent-1"
        assert values[":student_id"] == "student-1"
        assert values[":relationship"] == paid_entitlement_service.BENEFICIARY_RELATIONSHIP
        assert values[":active"] == "active"
        for clause in ("#entity_type=:entity_type", "parent_id=:parent_id",
                       "student_id=:student_id", "relationship=:relationship",
                       "#status=:active"):
            assert clause in body["ConditionExpression"]


def test_a_paid_admission_fences_neither_binding_rows_nor_the_profile_pointer() -> None:
    checks = _checks(_scope())
    # The retired binding rows grant nothing, so nothing asserts them.
    assert ("USER#parent-1", "CHILD#student-1") not in checks
    assert ("USER#student-1", "PARENT#parent-1") not in checks
    profile = checks[("USER#student-1", "PROFILE")]
    # A link is not mirrored onto the profile, so the profile is not asked to claim it.
    assert "parent_id" not in profile["ConditionExpression"]
    assert "parent_binding_status" not in profile["ConditionExpression"]
    assert ":parent_id" not in profile["ExpressionAttributeValues"]
