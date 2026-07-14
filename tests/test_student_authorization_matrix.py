"""T-472-05/06/07 actor-resource-action-purpose matrix with positive controls."""

import pytest

from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationFacts,
    AuthorizationPolicy,
    AuthorizationPurpose,
    AuthorizationSpec,
    AuthorizedResource,
    ParentAuthorizationFacts,
    ResourceRef,
    ResourceType,
    authorize_and_resolve,
)
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
from stoa.security.identity import AccountStatus, Actor, CanonicalRole


MATRIX = [
    # family, actor, relation, action, purpose, expected
    ("students", "student", "owner", "read", "self_service", True),
    ("students", "parent", "unrelated", "read", "parent_oversight", False),
    ("questions", "teacher", "assigned", "read", "teacher_help", True),
    ("questions", "teacher", "unassigned", "read", "teacher_help", False),
    ("conversations", "student", "owner", "read", "self_service", True),
    ("conversations", "parent", "revoked_binding", "read", "parent_oversight", False),
    ("practice", "student", "owner", "update", "self_service", True),
    ("practice", "admin", "role_only", "read", "support", False),
    ("adaptive", "parent", "active_bidirectional_binding", "read", "parent_oversight", True),
    ("adaptive", "parent", "one_sided_binding", "read", "parent_oversight", False),
    ("reports", "parent", "active_bidirectional_binding", "read", "parent_oversight", True),
    ("reports", "teacher", "unassigned", "read", "teacher_help", False),
    ("teacher_help", "teacher", "dispatched", "respond", "teacher_help", True),
    ("teacher_help", "teacher", "other_dispatch", "respond", "teacher_help", False),
    ("admin_support", "admin", "scoped_grant", "read", "support", True),
    ("admin_support", "admin", "role_only", "read", "support", False),
]


@pytest.mark.parametrize(
    "family,actor,relation,action,purpose,expected",
    MATRIX,
    ids=[f"T-472-06-{row[0]}-{row[1]}-{row[2]}-{'allow' if row[-1] else 'deny'}" for row in MATRIX],
)
def test_student_resource_authorization_matrix(
    family, actor, relation, action, purpose, expected
):
    from stoa.security.authorization import evaluate_matrix_case

    decision = evaluate_matrix_case(
        family=family,
        actor=actor,
        relation=relation,
        action=action,
        purpose=purpose,
    )
    assert decision.allowed is expected


def test_t472_07_hidden_resource_real_and_random_ids_are_indistinguishable():
    from stoa.security.authorization import evaluate_hidden_resource_case

    real = evaluate_hidden_resource_case("known-student-resource")
    random = evaluate_hidden_resource_case("random-nonexistent-resource")
    assert real.status_code == random.status_code == 404
    assert real.body == random.body


def _actor(role: CanonicalRole, user_id: str) -> Actor:
    return Actor(
        user_id=user_id,
        issuer="https://identity.test",
        subject=f"{user_id}-subject",
        role=role,
        account_status=AccountStatus.ACTIVE,
        cognito_group=role.value,
    )


def _parent_resource(facts: ParentAuthorizationFacts) -> AuthorizedResource:
    ref = ResourceRef(
        ResourceType.ADAPTIVE_PROFILE,
        "adaptive-1",
        "student-1",
        relationship_known=True,
    )
    return AuthorizedResource(ref, {"profile_id": "adaptive-1"}, AuthorizationFacts(parent=facts))


@pytest.mark.parametrize(
    ("mutation", "allowed"),
    [
        (None, True),
        ("legacy_only", False),
        ("pending", False),
        ("revoked", False),
        ("asymmetric", False),
        ("stale_version", False),
        ("inactive_parent", False),
        ("inactive_student", False),
    ],
)
def test_parent_requires_matching_active_bidirectional_current_facts(mutation, allowed):
    row = {
        "parent_id": "parent-1",
        "student_id": "student-1",
        "relationship": "child",
        "status": "active",
        "version": 4,
    }
    forward = dict(row)
    reverse = dict(row)
    parent = {"user_id": "parent-1", "role": "parent", "account_status": "active"}
    student = {"user_id": "student-1", "role": "student", "account_status": "active"}
    if mutation == "legacy_only":
        forward = reverse = None
        student["parent_id"] = "parent-1"
    elif mutation in {"pending", "revoked"}:
        forward["status"] = reverse["status"] = mutation
    elif mutation == "asymmetric":
        reverse = None
    elif mutation == "stale_version":
        reverse["version"] = 3
    elif mutation == "inactive_parent":
        parent["account_status"] = "suspended"
    elif mutation == "inactive_student":
        student["account_status"] = "revoked"

    decision = AuthorizationPolicy().evaluate(
        _actor(CanonicalRole.PARENT, "parent-1"),
        _parent_resource(ParentAuthorizationFacts(forward, reverse, parent, student)),
        AuthorizationAction.READ,
        AuthorizationPurpose.PARENT_OVERSIGHT,
    )
    assert decision.allowed is allowed


@pytest.mark.asyncio
async def test_resolver_returns_exact_authorized_object_and_outage_prevents_handler():
    loaded = {"student_id": "student-1", "answer": "private"}
    resolver_calls = []
    handler_calls = []

    async def resolver(resource_id):
        resolver_calls.append(resource_id)
        return loaded

    class OwnerFacts:
        async def facts_for(self, *_args):
            return AuthorizationFacts()

    resolved = await authorize_and_resolve(
        actor=_actor(CanonicalRole.STUDENT, "student-1"),
        resource_id="question-1",
        spec=AuthorizationSpec(
            ResourceType.QUESTION,
            AuthorizationAction.READ,
            AuthorizationPurpose.SELF_SERVICE,
            resolver,
        ),
        fact_repository=OwnerFacts(),
    )
    handler_calls.append(resolved.value)
    assert resolved.value is loaded
    assert resolver_calls == ["question-1"]
    assert handler_calls == [loaded]

    class OutageFacts:
        async def facts_for(self, *_args):
            raise TimeoutError("authorization canary")

    with pytest.raises(SecurityDecisionError) as outage:
        await authorize_and_resolve(
            actor=_actor(CanonicalRole.STUDENT, "student-1"),
            resource_id="question-2",
            spec=AuthorizationSpec(
                ResourceType.QUESTION,
                AuthorizationAction.READ,
                AuthorizationPurpose.SELF_SERVICE,
                resolver,
            ),
            fact_repository=OutageFacts(),
        )
    assert outage.value.code is SecurityErrorCode.AUTHORIZATION_TEMPORARILY_UNAVAILABLE
    assert "authorization canary" not in repr(outage.value.public_body())
    assert handler_calls == [loaded]
