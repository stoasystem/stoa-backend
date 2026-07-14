"""T-472-08 executable sensitive-route authorization inventory mutation tests."""

from fastapi import APIRouter, FastAPI


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
