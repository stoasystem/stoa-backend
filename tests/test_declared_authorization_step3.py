"""Declarative authorization, step 3 (#350, shape in #316).

The old factories are gone, and the route inventory reads only what the
entry generates. Metadata pasted onto a dependency by hand turns the gate
red, and no module but the entry may set it.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from audit_helpers import MemoryAuthorizationAuditSink
from stoa.deps import get_actor, get_authorization_audit_sink
from stoa.security.authorization import (
    AuthorizationAction,
    AuthorizationPurpose,
    AuthorizationSpec,
    ResourceType,
)
from stoa.security.declared_authorization import SELF, authorized, safe_public
from stoa.security.identity import AccountStatus, Actor, CanonicalRole
from stoa.security.route_inventory import inventory_application, validate_application_inventory

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "stoa"
ENTRY = SOURCE / "security" / "declared_authorization.py"
STUDENT_SELF = {CanonicalRole.STUDENT: AuthorizationPurpose.SELF_SERVICE}

STUDENT = Actor(
    user_id="student-1",
    issuer="https://identity.test",
    subject="student-1-subject",
    role=CanonicalRole.STUDENT,
    account_status=AccountStatus.ACTIVE,
    cognito_group="student",
    current_grants=(),
)


async def _resolve(resource_id: str):
    return {"student_id": resource_id}


def _pasted_spec() -> tuple[AuthorizationSpec, ...]:
    return (
        AuthorizationSpec(
            ResourceType.STUDENT,
            AuthorizationAction.READ,
            AuthorizationPurpose.SELF_SERVICE,
            _resolve,
        ),
    )


def _failures(app: FastAPI) -> list[str]:
    return [failure.reason for failure in validate_application_inventory(app)]


# ---------------------------------------------------------------------------
# The gate: the inventory only reads what the entry generates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "attribute,value",
    [
        ("authorization_specs", _pasted_spec()),
        ("required_capability", "teacher_identity_reviewer"),
        ("safe_public", True),
    ],
)
def test_metadata_pasted_onto_a_dependency_turns_the_gate_red(attribute, value):
    async def pasted(actor: Actor = Depends(get_actor)) -> Actor:
        return actor

    setattr(pasted, attribute, value)
    app = FastAPI()

    @app.get("/students/{student_id}")
    def read(student_id: str, _actor: Actor = Depends(pasted)) -> dict[str, str]:
        return {"student_id": student_id}

    failures = _failures(app)
    assert any(f"pasted {attribute}" in reason for reason in failures), failures
    with pytest.raises(ValueError, match=f"pasted {attribute}"):
        inventory_application(app)


def test_specs_pasted_next_to_a_real_declaration_still_turn_the_gate_red():
    """A pasted note cannot ride along on a route the entry also authorizes."""

    async def pasted(actor: Actor = Depends(get_actor)) -> Actor:
        return actor

    pasted.authorization_specs = _pasted_spec()  # type: ignore[attr-defined]
    app = FastAPI()

    @app.get(
        "/students/me/thing",
        dependencies=[
            Depends(authorized(ResourceType.UPLOAD, AuthorizationAction.READ, SELF, STUDENT_SELF)),
            Depends(pasted),
        ],
    )
    def read() -> dict[str, str]:
        return {}

    assert any("pasted authorization_specs" in reason for reason in _failures(app))


def test_specs_pasted_onto_the_endpoint_turn_the_gate_red():
    app = FastAPI()

    @app.get(
        "/students/me/thing",
        dependencies=[
            Depends(authorized(ResourceType.UPLOAD, AuthorizationAction.READ, SELF, STUDENT_SELF)),
        ],
    )
    def read() -> dict[str, str]:
        return {}

    read.authorization_specs = _pasted_spec()  # type: ignore[attr-defined]
    assert any("pasted authorization_specs" in reason for reason in _failures(app))


def test_a_route_declared_through_the_entry_passes_the_gate():
    app = FastAPI()

    @app.get(
        "/students/me/thing",
        dependencies=[
            Depends(authorized(ResourceType.UPLOAD, AuthorizationAction.READ, SELF, STUDENT_SELF)),
        ],
    )
    def read() -> dict[str, str]:
        return {}

    assert _failures(app) == []


# ---------------------------------------------------------------------------
# safe_public is one of the entry's declarations
# ---------------------------------------------------------------------------


def test_safe_public_is_declared_through_the_entry_and_hands_over_the_actor():
    app = FastAPI()

    @app.get("/practice/catalog")
    def catalog(actor: Actor = Depends(safe_public(ResourceType.PRACTICE))) -> dict[str, str]:
        return {"actor": actor.user_id}

    (item,) = inventory_application(app)
    assert item.classification == "safe-public"
    assert [(spec.resource_type, spec.action, spec.purpose, spec.capability)
            for spec in item.authorization_specs] == [
        ("practice", "read", "self_service", None)
    ]
    sink = MemoryAuthorizationAuditSink()
    app.dependency_overrides[get_actor] = lambda: STUDENT
    app.dependency_overrides[get_authorization_audit_sink] = lambda: sink
    response = TestClient(app).get("/practice/catalog")
    assert response.status_code == 200
    assert response.json() == {"actor": "student-1"}
    assert sink.events == {}


# ---------------------------------------------------------------------------
# Only the entry sets authorization metadata
# ---------------------------------------------------------------------------

#: Attributes the inventory reads (the declaration) or used to read (the rest).
METADATA = frozenset(
    {"authorization_declaration", "authorization_specs", "required_capability", "safe_public"}
)


def _metadata_writes(source: str) -> list[tuple[int, str]]:
    """Every assignment or ``setattr`` of an authorization metadata attribute."""
    writes: list[tuple[int, str]] = []
    for node in ast.walk(ast.parse(source)):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign | ast.AugAssign):
            targets = [node.target]
        for target in targets:
            for part in ast.walk(target):
                if isinstance(part, ast.Attribute) and part.attr in METADATA:
                    writes.append((node.lineno, part.attr))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
            and len(node.args) >= 2
        ):
            name = node.args[1]
            if not isinstance(name, ast.Constant) or not isinstance(name.value, str):
                writes.append((node.lineno, "<computed setattr>"))
            elif name.value in METADATA:
                writes.append((node.lineno, name.value))
    return writes


@pytest.mark.parametrize(
    "snippet",
    [
        "dependency.authorization_specs = ()",
        "dependency.authorization_specs: tuple = ()",
        "setattr(dependency, 'authorization_specs', ())",
        "setattr(dependency, 'safe_public', True)",
        "setattr(dependency, 'required_capability', 'x')",
        "dependency.authorization_declaration = declaration",
        "a = b.authorization_specs = ()",
    ],
)
def test_the_scan_sees_a_pasted_note(snippet):
    assert _metadata_writes(snippet)


def test_the_scan_ignores_reading_the_metadata():
    assert _metadata_writes("specs = getattr(call, 'authorization_specs', ())") == []
    assert _metadata_writes("specs = call.authorization_specs") == []


def test_no_module_but_the_entry_sets_authorization_metadata():
    pasted = {
        f"{path.relative_to(ROOT).as_posix()}:{line}:{name}"
        for path in sorted(SOURCE.rglob("*.py"))
        if path != ENTRY
        for line, name in _metadata_writes(path.read_text(encoding="utf-8"))
    }
    assert pasted == set()


def test_the_entry_sets_only_the_declaration():
    names = {name for _line, name in _metadata_writes(ENTRY.read_text(encoding="utf-8"))}
    assert names == {"authorization_declaration"}


# ---------------------------------------------------------------------------
# The old factories and the dead teacher-dispatch purpose are gone
# ---------------------------------------------------------------------------


def test_the_old_factory_module_is_gone():
    assert importlib.util.find_spec("stoa.security.route_authorization") is None


def test_the_dead_teacher_dispatch_purpose_is_gone():
    assert "TEACHER_DISPATCH" not in AuthorizationPurpose.__members__
    source = (SOURCE / "security" / "authorization.py").read_text(encoding="utf-8")
    assert "teacher_dispatch_operator" not in source
