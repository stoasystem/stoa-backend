"""#34 / #85: the admission fences the relationship rows the profile check skips.

`paid_entitlement_service.relationship_authority` believes a student profile's
`parent_id` and `parent_binding_status` without reading the two binding rows.
That is only sound because the teacher-support admission transaction asserts
those rows itself. These tests hold the transaction to that.
"""

from __future__ import annotations

from typing import Any

import pytest

from stoa.models.allowance import TeacherSupportScope
from stoa.models.billing import BillingPlanId
from stoa.services import paid_entitlement_service
from stoa.services import teacher_support_allowance_service as allowance


def _scope(source: str, **overrides: Any) -> allowance._ResolvedScope:
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
        "relationship_source": source,
        "forward_relationship_version": 7,
        "reverse_relationship_version": 8,
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


def test_a_binding_admission_fences_both_binding_rows_at_their_versions() -> None:
    checks = _checks(_scope(paid_entitlement_service.RELATIONSHIP_SOURCE_BINDING))
    forward = checks[("USER#parent-1", "CHILD#student-1")]
    reverse = checks[("USER#student-1", "PARENT#parent-1")]
    for body, version in ((forward, 7), (reverse, 8)):
        values = body["ExpressionAttributeValues"]
        assert values[":parent_id"] == "parent-1"
        assert values[":student_id"] == "student-1"
        assert values[":relationship"] == paid_entitlement_service.BENEFICIARY_RELATIONSHIP
        assert values[":active"] == "active"
        assert values[":version"] == version
        for clause in ("parent_id=:parent_id", "student_id=:student_id", "#status=:active",
                       "#version=:version"):
            assert clause in body["ConditionExpression"]


def test_a_binding_admission_also_fences_the_profile_claim() -> None:
    checks = _checks(_scope(paid_entitlement_service.RELATIONSHIP_SOURCE_BINDING))
    profile = checks[("USER#student-1", "PROFILE")]
    assert "parent_id=:parent_id" in profile["ConditionExpression"]
    assert "parent_binding_status=:active" in profile["ConditionExpression"]
    assert profile["ExpressionAttributeValues"][":parent_id"] == "parent-1"


def test_a_link_admission_fences_both_link_rows_instead() -> None:
    checks = _checks(_scope(paid_entitlement_service.RELATIONSHIP_SOURCE_LINK))
    assert ("PARENT#parent-1", "CHILD#student-1") in checks
    assert ("STUDENT#student-1", "PARENT#parent-1") in checks
    assert ("USER#parent-1", "CHILD#student-1") not in checks
    profile = checks[("USER#student-1", "PROFILE")]
    # A link is not mirrored onto the profile, so the profile is not asked to claim it.
    assert "parent_binding_status" not in profile["ConditionExpression"]


def test_a_binding_admission_without_recorded_versions_is_refused() -> None:
    scope = _scope(
        paid_entitlement_service.RELATIONSHIP_SOURCE_BINDING, forward_relationship_version=None
    )
    with pytest.raises(ValueError):
        allowance._grant_condition_operations(scope)
