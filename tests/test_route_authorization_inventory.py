"""T-472-08 executable registered-route authorization inventory tests."""

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel, Field

from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    ResourceType,
)
from stoa.security.route_inventory import explicit_route_classification


SENSITIVE_ROUTE_FAMILIES = {
    "students",
    "questions",
    "conversations",
    "practice",
    "adaptive",
    "reports",
    "teachers",
    "parents",
    "admin",
    "notifications",
}


def test_t472_08_inventory_has_every_sensitive_route_family_and_policy_metadata():
    from stoa.security.route_inventory import inventory_application

    from stoa.main import app

    inventory = inventory_application(app)
    assert SENSITIVE_ROUTE_FAMILIES <= {item.family for item in inventory}
    assert all(item.authorization_spec is not None for item in inventory if item.sensitive)
    assert len(inventory) == len({(item.method, item.path) for item in inventory})


def test_t472_08_inventory_mutation_rejects_synthetic_unclassified_sensitive_route():
    from stoa.security.route_inventory import validate_application_inventory

    app = FastAPI()
    router = APIRouter()

    @router.get("/students/{student_id}/synthetic-sensitive")
    def synthetic_sensitive(student_id: str):
        return {"studentId": student_id}

    app.include_router(router)
    failures = validate_application_inventory(app)
    assert any("synthetic-sensitive" in failure.path for failure in failures)


def test_inventory_rejects_every_new_unclassified_registered_router():
    from stoa.security.route_inventory import validate_application_inventory

    app = FastAPI()
    router = APIRouter()

    @router.get("/new-global-route")
    def newly_registered():
        return {}

    app.include_router(router)
    assert validate_application_inventory(app) == (
        validate_application_inventory(app)[0],
    )
    assert "no executable authorization" in validate_application_inventory(app)[0].reason


def test_event_id_and_push_token_body_mutations_require_actor_owner_policy():
    from stoa.security.route_inventory import validate_application_inventory

    class PushBody(BaseModel):
        provider_token_reference: str = Field(alias="providerTokenReference")
        device_id: str = Field(alias="deviceId")

    app = FastAPI()

    @app.post("/notifications/{event_id}/unsafe")
    @explicit_route_classification("authenticated-global", "synthetic mutation")
    def event_mutation(event_id: str):
        return {"eventId": event_id}

    @app.post("/notifications/push-token-unsafe")
    @explicit_route_classification("authenticated-global", "synthetic mutation")
    def token_mutation(body: PushBody):
        return body

    failures = validate_application_inventory(app)
    assert {failure.path for failure in failures} == {
        "/notifications/{event_id}/unsafe",
        "/notifications/push-token-unsafe",
    }


def test_notification_identifier_rejects_unrelated_executable_spec():
    from stoa.security.route_inventory import validate_application_inventory

    async def resolver(resource_id: str):
        return {"student_id": resource_id}

    async def wrong_dependency():
        return None

    wrong_dependency.authorization_specs = (
        AuthorizationSpec(
            ResourceType.STUDENT,
            AuthorizationAction.READ,
            AuthorizationPurpose.SELF_SERVICE,
            resolver,
        ),
    )
    app = FastAPI()

    @app.get("/notifications/{event_id}")
    def unsafe_event(event_id: str, _: None = Depends(wrong_dependency)):
        return {"eventId": event_id}

    failures = validate_application_inventory(app)
    assert len(failures) == 1
    assert "Actor-owner" in failures[0].reason


def test_openapi_and_checked_json_are_identical_runtime_projections():
    import json
    from pathlib import Path

    from stoa.main import app
    from stoa.security.route_inventory import inventory_application

    checked = json.loads(Path("docs/security/route-authorization-inventory.json").read_text())
    runtime = [item.projection() for item in inventory_application(app)]
    assert checked == runtime
    schema = app.openapi()
    for item in runtime:
        extension = schema["paths"][item["path"]][item["method"].lower()][
            "x-stoa-authorization"
        ]
        assert extension == {
            "classification": item["classification"],
            "identifiers": item["identifiers"],
            "authorization": item["authorization"],
        }


def test_metadata_on_endpoint_without_dependency_is_rejected():
    from stoa.security.route_inventory import validate_application_inventory

    async def resolver(resource_id: str):
        return {"student_id": resource_id}

    app = FastAPI()

    @app.get("/students/{student_id}/metadata-only")
    def metadata_only(student_id: str):
        return {"studentId": student_id}

    metadata_only.authorization_specs = (
        AuthorizationSpec(
            ResourceType.STUDENT,
            AuthorizationAction.READ,
            AuthorizationPurpose.SELF_SERVICE,
            resolver,
        ),
    )
    failures = validate_application_inventory(app)
    assert any("not attached to a dependency" in failure.reason for failure in failures)
