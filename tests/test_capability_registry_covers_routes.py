"""The capabilities routes ask for must be capabilities somebody can be given.

Two lists describe the same thing from opposite ends. `admin_authorization`
names the capability each registered admin route demands, and that name reaches
`docs/security/route-authorization-inventory.json`. `capability_repo` holds the
only list a grant may be issued from: `grant_capability` refuses anything else
outright.

Nineteen names were in the first list and not the second, so forty-nine admin
routes refused every account that could ever exist - the platform dashboard, the
notification console, report operations, teacher dispatch, parent-binding
repair, usage inspection and the entire billing surface. Nothing reported it.
A route nobody can be authorised for and a route somebody is forbidden from
answer with the same `action_not_allowed`, so the console simply looked like it
was denying you, and the only way to tell the two apart was to read both lists.

These tests are that reading, done every run.
"""

from __future__ import annotations

import json
from pathlib import Path

from stoa.db.repositories import capability_repo


INVENTORY = Path(__file__).resolve().parents[1] / "docs" / "security" / "route-authorization-inventory.json"


def capabilities_routes_demand() -> dict[str, list[str]]:
    """Every capability named by a route, and the routes that name it.

    A policy may accept any one of several capabilities, which the inventory
    writes as `a|b`. Each alternative has to be issuable on its own: a route
    guarded by `curriculum_reviewer|curriculum_publisher` is unreachable for a
    reviewer if only the publisher name can be granted.
    """
    demanded: dict[str, list[str]] = {}
    for route in json.loads(INVENTORY.read_text(encoding="utf-8")):
        for entry in route.get("authorization", []):
            capability = entry.get("capability")
            if not capability:
                continue
            for name in str(capability).split("|"):
                demanded.setdefault(name.strip(), []).append(
                    f"{route['method']} {route['path']}"
                )
    return demanded


def test_every_capability_a_route_demands_can_actually_be_granted() -> None:
    demanded = capabilities_routes_demand()
    assert demanded, "the inventory named no capabilities; the reader is broken"

    ungrantable = {
        name: routes
        for name, routes in sorted(demanded.items())
        if name not in capability_repo.KNOWN_CAPABILITIES
    }

    assert not ungrantable, (
        "these capabilities gate registered routes and no grant can issue them, "
        "so those routes refuse everybody: "
        + json.dumps({name: len(routes) for name, routes in ungrantable.items()}, indent=2)
    )


def test_the_registry_names_nothing_no_route_asks_for() -> None:
    """The other direction, so the registry cannot fill up with dead names.

    Two are expected: `student_content_review` and `student_data_break_glass`
    are held by paths that judge them outside the admin route table, so they are
    named here rather than left to drift. Anything else is either a route that
    lost its guard or a name nobody ever used.
    """
    judged_elsewhere = {"student_content_review", "student_data_break_glass"}

    unused = sorted(
        set(capability_repo.KNOWN_CAPABILITIES)
        - set(capabilities_routes_demand())
        - judged_elsewhere
    )

    assert unused == [], f"registry names no route asks for: {unused}"


def test_the_reader_finds_the_capabilities_it_claims_to_check() -> None:
    """Negative control: an empty reading would pass both checks above silently."""
    demanded = capabilities_routes_demand()

    assert len(demanded) >= 25, f"only {len(demanded)} capabilities read from the inventory"
    assert "admin_identity_manager" in demanded
    assert demanded["admin_identity_manager"], "no routes recorded against a known capability"


def test_an_alternative_in_a_pair_is_read_as_its_own_capability() -> None:
    """`a|b` has to yield both names, or half the registry goes unchecked."""
    demanded = capabilities_routes_demand()

    assert "curriculum_reviewer" in demanded
    assert "curriculum_publisher" in demanded
