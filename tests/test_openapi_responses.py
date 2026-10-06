"""What OpenAPI declares about responses the frontend's mocks are checked against (#81)."""

from __future__ import annotations

from botocore.exceptions import ClientError
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from stoa.config import Settings, get_settings
from stoa.main import app
from stoa.models import error as error_models
from stoa.routers import auth
from stoa.security.errors import SecurityDecisionError, SecurityErrorCode
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


def test_bearer_operations_declare_the_shared_401():
    schema = _schema()
    declared = []
    for item in inventory_application(app):
        operation = schema["paths"][item.path][item.method.lower()]
        if operation.get("security"):
            assert "401" in operation["responses"], f"{item.method} {item.path}"
            declared.append(operation["responses"]["401"]["content"]["application/json"]["schema"])

    # One shared component, not a copy per operation.
    assert declared and all(ref == {"$ref": "#/components/schemas/UnauthenticatedResponse"} for ref in declared)
    body = _resolve(schema, declared[0])
    variants = _detail_variants(schema, body)
    # HTTPBearer answers a missing header with a sentence; the token verifier
    # answers a bad or expired token with the security body.
    assert {"type": "string"} in [{"type": item.get("type")} for item in variants]
    assert any(_is_error_body(item) for item in variants)


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/adaptive/students/me/memory", "get"),
        ("/practice/subjects", "get"),
        ("/auth/me", "get"),
        ("/teacher-applications/activation/consume", "post"),
    ],
)
def test_sample_bearer_routes_declare_401(path, method):
    operation = _schema()["paths"][path][method]
    assert "401" in operation["responses"]


def test_a_route_that_never_answers_401_declares_none():
    assert "401" not in _schema()["paths"]["/health"]["get"]["responses"]


# ── 401 from the tokenless sign-in operations ─────────────────────────────────
#
# These answer a refusal from the identity provider with the security body at the
# top level (no `detail` envelope), so they cannot share the bearer 401.


def _auth_settings() -> Settings:
    return Settings(
        aws_region="eu-central-2",
        cognito_user_pool_id="offline-pool",
        cognito_student_client_id="student-client",
        cognito_parent_client_id="parent-client",
        cognito_teacher_client_id="teacher-client",
        cognito_admin_client_id="admin-client",
    )


def _auth_client() -> TestClient:
    bare = FastAPI()
    bare.include_router(auth.router, prefix="/auth")
    bare.dependency_overrides[get_settings] = _auth_settings
    return TestClient(bare)


class _Cognito:
    """Refuses with one provider code, or signs in with an opaque token."""

    def __init__(self, refusal: str | None = None):
        self.refusal = refusal

    def _answer(self, operation: str):
        if self.refusal:
            raise ClientError({"Error": {"Code": self.refusal, "Message": "refused"}}, operation)
        return {"AuthenticationResult": {"AccessToken": "opaque-access-token"}}

    def initiate_auth(self, **_kwargs):
        return self._answer("InitiateAuth")

    def global_sign_out(self, **_kwargs):
        return self._answer("GlobalSignOut")


def _declared_401_model(path: str):
    operation = _schema()["paths"][path]["post"]
    assert "401" in operation["responses"], f"POST {path} does not declare 401"
    ref = operation["responses"]["401"]["content"]["application/json"]["schema"]["$ref"]
    return getattr(error_models, ref.rsplit("/", 1)[-1])


@pytest.mark.parametrize(
    ("path", "payload", "code"),
    [
        ("/auth/login", {"email": "student@example.com", "password": "wrong-password"}, "invalid_credentials"),
        ("/auth/refresh", {"refresh_token": "revoked-refresh"}, "invalid_token"),
        ("/auth/logout", {"access_token": "revoked-access"}, "invalid_token"),
    ],
)
def test_sign_in_operations_declare_the_provider_refusal_they_send(monkeypatch, path, payload, code):
    monkeypatch.setattr(auth, "_get_cognito", lambda _settings: _Cognito("NotAuthorizedException"))

    response = _auth_client().post(path, json=payload)

    assert response.status_code == 401
    assert response.json()["code"] == code
    _declared_401_model(path).model_validate(response.json())


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/auth/login", {"email": "student@example.com", "password": "ValidPass123!"}),
        ("/auth/refresh", {"refresh_token": "valid-refresh"}),
    ],
)
def test_sign_in_operations_declare_the_refused_issued_token(monkeypatch, path, payload):
    # The provider accepted, but the token it issued does not verify here: the
    # route answers with the security body inside `detail`.
    monkeypatch.setattr(auth, "_get_cognito", lambda _settings: _Cognito())

    async def _refuse(*_args, **_kwargs):
        raise SecurityDecisionError(SecurityErrorCode.TOKEN_EXPIRED)

    monkeypatch.setattr(auth.public_identity_service, "resolve_account_access_token", _refuse)

    response = _auth_client().post(path, json=payload)

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "token_expired"
    _declared_401_model(path).model_validate(response.json())


def test_creating_a_conversation_declares_the_first_message_refusal_naming_it() -> None:
    # #61: a refused first message names the conversation already made.
    schema = app.openapi()
    responses = schema["paths"]["/conversations"]["post"]["responses"]
    assert _declared_models(responses, 429) == [error_models.FirstMessageRefusalResponse]
    for code in (409, 503):
        assert error_models.FirstMessageRefusalResponse in _declared_models(responses, code)
    body = schema["components"]["schemas"]["FirstMessageRefusalBody"]
    assert {"code", "message", "conversationId"} <= set(body["required"])


def _declared_models(responses: dict, code: int) -> list[type]:
    schema = responses[str(code)]["content"]["application/json"]["schema"]
    refs = [item["$ref"] for item in schema.get("anyOf", [schema])]
    return [getattr(error_models, ref.rsplit("/", 1)[-1]) for ref in refs]


@pytest.mark.parametrize("outage, expected", [(False, 409), (True, 503)])
def test_creating_a_conversation_declares_the_identity_refusal_made_before_it(
    monkeypatch: pytest.MonkeyPatch, outage: bool, expected: int
) -> None:
    # Review of 862988d7: before any conversation exists the identity check
    # answers 409 (no binding) or 503 (store unavailable), with no conversationId.
    from pydantic import TypeAdapter, ValidationError

    from stoa.deps import get_identity_repository, get_verified_token
    from stoa.routers import conversations
    from stoa.security.tokens import VerifiedAccessToken

    class _Repository:
        async def get_binding(self, issuer: str, subject: str) -> None:
            if outage:
                raise TimeoutError("identity store unavailable")
            return None

    created: list[bool] = []
    monkeypatch.setattr(conversations, "get_table", lambda: created.append(True))
    route_app = FastAPI()
    route_app.include_router(conversations.router, prefix="/conversations")
    route_app.dependency_overrides[get_verified_token] = lambda: VerifiedAccessToken(
        issuer="https://identity.test/primary",
        subject="subject-1",
        client_id="student-client",
        groups=("students",),
    )
    route_app.dependency_overrides[get_identity_repository] = _Repository

    response = TestClient(route_app).post(
        "/conversations",
        json={"subject": "Mathematik", "grade": "Grade 6", "initialMessage": "Help"},
    )

    assert response.status_code == expected, response.text
    assert created == []
    declared = _declared_models(app.openapi()["paths"]["/conversations"]["post"]["responses"], expected)
    assert set(declared) == {error_models.SecurityErrorResponse, error_models.FirstMessageRefusalResponse}
    union = TypeAdapter(error_models.SecurityErrorResponse | error_models.FirstMessageRefusalResponse)
    union.validate_python(response.json())
    with pytest.raises(ValidationError):
        error_models.FirstMessageRefusalResponse.model_validate(response.json())
