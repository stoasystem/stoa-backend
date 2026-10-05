"""What OpenAPI declares about responses the frontend's mocks are checked against (#81)."""

from __future__ import annotations

import pytest

from stoa.main import app
from stoa.security.route_inventory import inventory_application


def _schema() -> dict:
    return app.openapi()


def _resolve(schema: dict, node: dict) -> dict:
    while "$ref" in node:
        node = schema["components"]["schemas"][node["$ref"].rsplit("/", 1)[-1]]
    return node


def _body(schema: dict, path: str, method: str, status: str) -> dict:
    operation = schema["paths"][path][method]
    assert status in operation["responses"], f"{method.upper()} {path} does not declare {status}"
    return _resolve(schema, operation["responses"][status]["content"]["application/json"]["schema"])


def _detail_variants(schema: dict, body: dict) -> list[dict]:
    detail = body["properties"]["detail"]
    return [_resolve(schema, item) for item in detail.get("anyOf", [detail])]


def _is_error_body(node: dict) -> bool:
    return set(node.get("properties", {})) == {"code", "message", "correlationId"} and set(
        node.get("required", [])
    ) == {"code", "message", "correlationId"}


def test_memory_summary_declares_the_fields_the_handler_returns():
    schema = _schema()
    body = _body(schema, "/adaptive/students/me/memory", "get", "200")

    assert set(body["properties"]) == {
        "studentId",
        "roleView",
        "locale",
        "subjects",
        "subjectActivity",
        "weakTopics",
        "strengthTopics",
        "memorySnapshots",
        "recommendations",
        "sequencingSummary",
        "freshness",
        "updatedAt",
    }
    assert set(body["required"]) == set(body["properties"])
    # The other two routes that return the same summary declare the same model.
    me = _schema_of(schema, "/adaptive/students/me/memory", "get")
    assert _schema_of(schema, "/adaptive/students/{student_id}/memory", "get") == me
    assert _schema_of(schema, "/adaptive/students/{student_id}/memory/refresh", "post") == me


def _schema_of(schema: dict, path: str, method: str) -> dict:
    return schema["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]


def test_generation_progress_declares_the_unknown_command_conflict():
    schema = _schema()
    body = _body(schema, "/conversations/{conv_id}/generation", "get", "409")

    (detail,) = _detail_variants(schema, body)
    assert _is_error_body(detail)
    assert "message_command_not_found" in _resolve(schema, detail["properties"]["code"])["enum"]


def test_teacher_help_status_declares_never_escalated_as_not_found():
    schema = _schema()
    body = _body(schema, "/teacher-help/conversations/{conv_id}/request", "get", "404")

    variants = _detail_variants(schema, body)
    # The plain sentence for a conversation that was never escalated, and the
    # security body for one the caller may not see.
    assert {"type": "string"} in [{"type": item.get("type")} for item in variants]
    assert any(_is_error_body(item) for item in variants)


def _item_schema(schema: dict, body: dict, field: str) -> dict:
    return _resolve(schema, body["properties"][field]["items"])


@pytest.mark.parametrize(
    ("field", "required"),
    [
        ("subjects", {"id", "label", "rolloutState"}),
        (
            "subjectActivity",
            {
                "subject",
                "label",
                "rolloutState",
                "questionCount",
                "aiResolvedCount",
                "teacherEscalationCount",
                "feedbackAverage",
            },
        ),
        # evidenceQuestionIds is declared but not required: a parent's view
        # leaves it out.
        ("weakTopics", {"subject", "topicId", "label", "count", "latestEvidenceAt"}),
        (
            "recommendations",
            {
                "candidateId",
                "type",
                "sourceType",
                "sourceId",
                "subject",
                "topicId",
                "label",
                "rationale",
                "confidence",
                "freshness",
                "sourceSignals",
                "reviewRequired",
                "autonomousDecision",
                "reviewFlags",
            },
        ),
    ],
)
def test_memory_summary_lists_declare_their_stable_item_fields(field, required):
    schema = _schema()
    body = _body(schema, "/adaptive/students/me/memory", "get", "200")
    item = _item_schema(schema, body, field)

    assert set(item.get("required", [])) == required
    assert required <= set(item["properties"])


def test_memory_weak_topics_declare_the_evidence_a_parent_does_not_see():
    schema = _schema()
    body = _body(schema, "/adaptive/students/me/memory", "get", "200")
    item = _item_schema(schema, body, "weakTopics")

    assert "evidenceQuestionIds" in item["properties"]
    assert "evidenceQuestionIds" not in item["required"]


def test_bearer_operations_declare_401_and_tokenless_ones_do_not():
    schema = _schema()
    declared = []
    for item in inventory_application(app):
        operation = schema["paths"][item.path][item.method.lower()]
        needs_token = bool(operation.get("security"))
        assert ("401" in operation["responses"]) is needs_token, (
            f"{item.method} {item.path} ({item.classification})"
        )
        if needs_token:
            declared.append(operation["responses"]["401"]["content"]["application/json"]["schema"])
        else:
            assert item.classification == "public", f"{item.method} {item.path}"

    # One shared component, not a copy per operation.
    assert declared and all(ref == declared[0] for ref in declared)
    body = _resolve(schema, declared[0])
    variants = _detail_variants(schema, body)
    # HTTPBearer answers a missing header with a sentence; the token verifier
    # answers a bad or expired token with the security body.
    assert {"type": "string"} in [{"type": item.get("type")} for item in variants]
    assert any(_is_error_body(item) for item in variants)


@pytest.mark.parametrize(
    ("path", "method", "expected"),
    [
        ("/adaptive/students/me/memory", "get", True),
        ("/practice/subjects", "get", True),
        ("/auth/me", "get", True),
        ("/teacher-applications/activation/consume", "post", True),
        ("/auth/login", "post", False),
        ("/health", "get", False),
    ],
)
def test_sample_routes_declare_401_only_where_a_token_is_required(path, method, expected):
    operation = _schema()["paths"][path][method]
    assert ("401" in operation["responses"]) is expected
