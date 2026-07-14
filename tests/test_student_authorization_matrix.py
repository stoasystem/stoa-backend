"""T-472-05/06/07 actor-resource-action-purpose matrix with positive controls."""

import pytest


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
