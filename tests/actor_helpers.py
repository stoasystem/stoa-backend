from fastapi import FastAPI

from stoa.deps import get_actor, get_current_user
from stoa.security.authorization import (
    AuthorizationFacts,
    ParentAuthorizationFacts,
    TeacherAuthorizationFacts,
)
from stoa.security.identity import (
    AccountStatus,
    Actor,
    CanonicalRole,
    CapabilityGrant,
)
from stoa.security.route_authorization import get_authorization_fact_repository


def actor_from_user(user: dict) -> Actor:
    role = CanonicalRole(user["role"])
    capabilities = user.get("grantCapabilities")
    if capabilities is None and role is CanonicalRole.ADMIN:
        capabilities = (
            "learning_assignment_manager",
            "assignment_automation_preview",
            "assignment_automation_execute",
            "student_content_review",
        )
    capabilities = capabilities or ()
    grants = (
        tuple(
            CapabilityGrant(name, str(user.get("grantScope") or "student:student-1"), 1)
            for name in capabilities
        )
    )
    return Actor(
        str(user["sub"]),
        "https://identity.test",
        f"{user['sub']}-subject",
        role,
        AccountStatus(user.get("accountStatus") or "active"),
        role.value,
        grants,
        tuple(
            (key, str(value))
            for key, value in user.items()
            if key in {"preferredLocale", "preferred_locale", "language"}
        ),
    )


def install_actor_overrides(app: FastAPI, user: dict) -> Actor:
    actor = actor_from_user(user)

    class Facts:
        async def facts_for(self, current_actor, resource, action, purpose, _value):
            student = {
                "user_id": resource.student_id,
                "role": "student",
                "account_status": "active",
            }
            if current_actor.role is CanonicalRole.PARENT and user.get("bound", True):
                row = {
                    "parent_id": current_actor.user_id,
                    "student_id": resource.student_id,
                    "relationship": "child",
                    "status": "active",
                    "version": 1,
                }
                return AuthorizationFacts(
                    parent=ParentAuthorizationFacts(
                        row,
                        dict(row),
                        {
                            "user_id": current_actor.user_id,
                            "role": "parent",
                            "account_status": "active",
                        },
                        student,
                    )
                )
            if current_actor.role is CanonicalRole.TEACHER and user.get("assigned", True):
                question = (
                    _value
                    if resource.resource_type.value == "question"
                    else None
                )
                return AuthorizationFacts(
                    teacher=TeacherAuthorizationFacts(
                        question=question,
                        assignment=None
                        if question
                        else {
                            "teacher_id": current_actor.user_id,
                            "student_id": resource.student_id,
                            "status": "active",
                            "resource_types": [resource.resource_type.value],
                            "actions": [action.value],
                            "purposes": [purpose.value],
                        },
                        teacher_account={
                            "user_id": current_actor.user_id,
                            "role": "teacher",
                            "account_status": current_actor.account_status.value,
                        },
                        student_account=student,
                    )
                )
            return AuthorizationFacts()

    app.dependency_overrides[get_actor] = lambda: actor
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_authorization_fact_repository] = Facts
    return actor
