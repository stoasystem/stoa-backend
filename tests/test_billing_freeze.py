"""Card 007: every paid route is frozen, and no new one may escape the freeze.

The judge here is deliberately not "the frozen list has 22 entries". A count
agrees with itself: add a 23rd paid route, forget to freeze it, and a count
test still passes while the new route serves payments. So the question is asked
the other way round -- the runtime route table is enumerated, every route that
carries paid meaning is picked out of it, and *each of those* has to refuse.
A newly added paid route is therefore judged the moment it is registered,
whether or not anyone remembered this file.
"""

from __future__ import annotations

import asyncio
import inspect
import re
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from actor_helpers import install_actor_overrides
from stoa.config import Settings, get_settings
from stoa.routers import admin, auth, billing, parents, students
from stoa.security.route_inventory import (
    explicit_route_classification,
    inventory_application,
)
from stoa.services import entitlement_service


# The vocabulary that makes a route a paid route. It is the vocabulary the
# codebase itself uses for money, so a new paid route written in the house
# style is caught by its own name.
PAID_VOCABULARY = re.compile(
    r"billing|subscription|checkout|stripe|refund|payment|invoice|price|pricing"
    r"|plan|purchase|charge|coupon|discount|tariff|paywall|wallet",
    re.IGNORECASE,
)

FROZEN_CODE = "billing_frozen"


def _full_app() -> FastAPI:
    """Main's router graph minus the one router it cannot project.

    Rebuilt here rather than imported from another card's test module: this is
    the closure judge for the freeze, and it must not go quiet because an
    unrelated test file was being edited at the time.
    """
    from stoa.routers import (
        adaptive,
        conversations,
        files,
        notifications,
        practice,
        questions,
        teacher_applications,
        teachers,
    )

    app = FastAPI()
    app.include_router(auth.router, prefix="/auth")
    app.include_router(conversations.router, prefix="/conversations")
    app.include_router(conversations.teacher_help_router, prefix="/teacher-help")
    app.include_router(practice.router, prefix="/practice")
    app.include_router(questions.router, prefix="/questions")
    app.include_router(students.router, prefix="/students")
    app.include_router(teachers.router, prefix="/teachers")
    app.include_router(teacher_applications.router, prefix="/teacher-applications")
    app.include_router(parents.router, prefix="/parents")
    app.include_router(billing.router, prefix="/billing")
    app.include_router(notifications.router, prefix="/notifications")
    app.include_router(notifications.admin_router, prefix="/admin")
    app.include_router(adaptive.router, prefix="/adaptive")
    app.include_router(admin.router, prefix="/admin")
    app.include_router(files.router, prefix="/files")

    @app.get("/health")
    @explicit_route_classification("public", "load-balancer health probe")
    def health_check() -> dict[str, str]:
        return {"status": "ok", "version": "0.1.0"}

    return app


def _carries_paid_meaning(route: APIRoute) -> bool:
    """Read the meaning off the registered route, not off any hand-kept list."""
    endpoint = route.endpoint
    if getattr(endpoint, "__module__", "") == billing.__name__:
        return True
    return bool(
        PAID_VOCABULARY.search(route.path)
        or PAID_VOCABULARY.search(getattr(endpoint, "__qualname__", ""))
    )


def paid_routes(app: FastAPI) -> dict[tuple[str, str], APIRoute]:
    """Every registered route that carries paid meaning, keyed by method+path.

    Read straight off `app.routes` rather than off the projected inventory, so
    a new paid route is judged even when it is too new to be classified.
    """
    found: dict[tuple[str, str], APIRoute] = {}
    for route in app.routes:
        if not isinstance(route, APIRoute) or not _carries_paid_meaning(route):
            continue
        for method in route.methods:
            if method in {"HEAD", "OPTIONS"}:
                continue
            found[(method, route.path)] = route
    return found


def _call_refusal(route: APIRoute) -> HTTPException | None:
    """Invoke the handler with nothing usable and report what it raised.

    A frozen handler refuses before it looks at a single argument, so `None`
    everywhere is enough to reach the refusal and not enough to do any work.
    Anything that answers, or raises something else, is not frozen.
    """
    endpoint = route.endpoint
    kwargs: dict[str, Any] = dict.fromkeys(inspect.signature(endpoint).parameters)
    try:
        result = endpoint(**kwargs)
        if inspect.isawaitable(result):
            asyncio.run(_await(result))
    except HTTPException as exc:
        return exc
    except BaseException:  # noqa: BLE001 - not a refusal either way
        return None
    return None


async def _await(awaitable: Any) -> Any:
    return await awaitable


def unfrozen_paid_routes(app: FastAPI) -> list[tuple[str, str]]:
    """The answer this card exists to keep empty."""
    escaped: list[tuple[str, str]] = []
    for key, route in sorted(paid_routes(app).items()):
        refusal = _call_refusal(route)
        if refusal is None or refusal.status_code != 410:
            escaped.append(key)
            continue
        detail = refusal.detail
        if not isinstance(detail, dict) or detail.get("code") != FROZEN_CODE:
            escaped.append(key)
    return escaped


# ---------------------------------------------------------------------------
# The closure judge
# ---------------------------------------------------------------------------


def test_no_registered_paid_route_escapes_the_freeze() -> None:
    assert unfrozen_paid_routes(_full_app()) == []


def test_the_judge_notices_a_newly_added_paid_route(capsys: Any) -> None:
    """Negative control, kept in the suite so the judge cannot go quiet.

    This is the poison the card demands, frozen into the test file: a paid
    route that nobody added to the freeze has to be reported. If this ever goes
    green the judge above is proving nothing.
    """
    del capsys
    app = _full_app()

    @app.get("/admin/subscriptions/billing/gift-cards")
    async def issue_gift_cards() -> dict[str, str]:
        return {"status": "sold"}

    assert unfrozen_paid_routes(app) == [
        ("GET", "/admin/subscriptions/billing/gift-cards")
    ]


def test_the_judge_reads_the_handler_not_the_path() -> None:
    """A paid route under an innocent path is still a paid route."""
    app = _full_app()

    @app.post("/admin/operations/run")
    async def execute_refund_batch() -> dict[str, str]:
        return {"status": "refunded"}

    assert unfrozen_paid_routes(app) == [("POST", "/admin/operations/run")]


def test_the_census_is_the_paid_surface_this_card_froze() -> None:
    """Drift alarm, not the judge: it also catches a paid route disappearing.

    Written out by hand so a wrong route wiring cannot agree with it.
    """
    assert set(paid_routes(_full_app())) == {
        ("POST", "/billing/webhooks/stripe"),
        ("GET", "/parents/me/subscription"),
        ("GET", "/parents/me/subscription/billing"),
        ("POST", "/parents/me/subscription/checkout"),
        ("GET", "/parents/me/subscription/checkout/{checkout_ref}"),
        ("POST", "/parents/me/subscription/checkout/{checkout_ref}/recheck"),
        ("POST", "/parents/me/subscription/checkout/{checkout_ref}/supersede"),
        ("GET", "/parents/me/subscription/requests"),
        ("POST", "/parents/me/subscription/requests"),
        ("GET", "/admin/billing/checkouts/{checkout_ref}"),
        ("POST", "/admin/billing/checkouts/{checkout_ref}/recheck"),
        ("GET", "/admin/subscriptions/billing"),
        ("GET", "/admin/subscriptions/billing/accounting-export"),
        ("GET", "/admin/subscriptions/billing/provider-readiness"),
        ("GET", "/admin/subscriptions/billing/rollout-controls"),
        ("PATCH", "/admin/subscriptions/billing/rollout-controls"),
        ("GET", "/admin/subscriptions/billing/{parent_id}"),
        ("POST", "/admin/subscriptions/billing/{parent_id}/refunds"),
        ("GET", "/admin/subscriptions/requests"),
        ("GET", "/admin/subscriptions/requests/{request_id}"),
        ("PATCH", "/admin/subscriptions/requests/{request_id}"),
        ("POST", "/admin/subscriptions/requests/{request_id}/apply"),
    }


def test_the_freeze_did_not_change_the_registered_route_table() -> None:
    """Freezing is a change of behaviour, never of the authorization inventory."""
    inventory = {(item.method, item.path) for item in inventory_application(_full_app())}
    assert set(paid_routes(_full_app())) <= inventory
    # The entitlement projection is not a paid route and must stay reachable:
    # it is how a free-tier student learns they are free tier.
    assert ("GET", "/students/me/entitlement") in inventory
    assert ("GET", "/students/me/entitlement") not in paid_routes(_full_app())


# ---------------------------------------------------------------------------
# The refusal a real client actually receives
# ---------------------------------------------------------------------------


def _settings() -> Settings:
    return Settings(cognito_user_pool_id="eu-central-2_test", aws_region="eu-central-2")


def _client(role: str, *, raise_server_exceptions: bool = True) -> TestClient:
    app = _full_app()
    app.dependency_overrides[get_settings] = _settings
    install_actor_overrides(
        app,
        {
            "sub": f"{role}-sub",
            "user_id": f"{role}-1",
            "email": f"{role}@stoa.test",
            "role": role,
        },
    )
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("GET", "/parents/me/subscription", None),
        ("GET", "/parents/me/subscription/billing", None),
        ("POST", "/parents/me/subscription/checkout", {"plan": "student", "beneficiaryIds": ["student-1"]}),
        ("GET", "/parents/me/subscription/checkout/ref-1", None),
        ("POST", "/parents/me/subscription/checkout/ref-1/recheck", {}),
        (
            "POST",
            "/parents/me/subscription/checkout/ref-1/supersede",
            {"confirmed": True, "plan": "student", "beneficiaryIds": ["student-1"]},
        ),
        ("GET", "/parents/me/subscription/requests", None),
        ("POST", "/parents/me/subscription/requests", {"request_type": "upgrade"}),
    ],
)
def test_a_signed_in_parent_is_refused_with_410(
    method: str, url: str, body: dict[str, Any] | None
) -> None:
    response = _client("parent").request(
        method, url, json=body, headers={"Idempotency-Key": "idem-key-1234"}
    )

    assert response.status_code == 410, response.text
    assert response.json()["detail"]["code"] == FROZEN_CODE


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("GET", "/admin/billing/checkouts/ref-1?parentId=parent-1", None),
        ("POST", "/admin/billing/checkouts/ref-1/recheck?parentId=parent-1", {}),
        ("GET", "/admin/subscriptions/billing", None),
        ("GET", "/admin/subscriptions/billing/accounting-export", None),
        ("GET", "/admin/subscriptions/billing/provider-readiness", None),
        ("GET", "/admin/subscriptions/billing/rollout-controls", None),
        (
            "PATCH",
            "/admin/subscriptions/billing/rollout-controls",
            {"checkoutState": "off", "reason": "frozen"},
        ),
        ("GET", "/admin/subscriptions/billing/parent-1", None),
        (
            "POST",
            "/admin/subscriptions/billing/parent-1/refunds",
            {"amount": 100, "reason": "support", "idempotencyKey": "idem-key-1234"},
        ),
        ("GET", "/admin/subscriptions/requests", None),
        ("GET", "/admin/subscriptions/requests/req-1", None),
        ("PATCH", "/admin/subscriptions/requests/req-1", {"status": "approved"}),
        ("POST", "/admin/subscriptions/requests/req-1/apply", {}),
    ],
)
def test_a_signed_in_admin_is_refused_with_410(
    method: str, url: str, body: dict[str, Any] | None
) -> None:
    response = _client("admin").request(method, url, json=body)

    assert response.status_code == 410, response.text
    assert response.json()["detail"]["code"] == FROZEN_CODE


def test_the_stripe_webhook_refuses_before_reading_a_signature() -> None:
    """No provider event may be admitted: the freeze answers first."""
    response = TestClient(_full_app()).post(
        "/billing/webhooks/stripe",
        content=b'{"id": "evt_1", "type": "checkout.session.completed"}',
        headers={"stripe-signature": "t=1,v1=deadbeef"},
    )

    assert response.status_code == 410, response.text
    assert response.json()["detail"]["code"] == FROZEN_CODE


def test_it_is_the_switch_that_refuses_not_the_harness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative control: with the switch back on, the same request is not a 410.

    It will fail some other way -- there is no payment provider to reach -- but
    it stops being the freeze's refusal, which is the whole point.
    """
    assert _client("parent").get("/parents/me/subscription").status_code == 410

    monkeypatch.setattr(billing, "BILLING_AND_SUBSCRIPTION_ENABLED", True)
    response = _client("parent", raise_server_exceptions=False).get(
        "/parents/me/subscription"
    )

    assert response.status_code != 410, response.text


# ---------------------------------------------------------------------------
# `manual_override`: the one paid bypass that is reachable without a route
# ---------------------------------------------------------------------------


def test_there_is_exactly_one_route_switch_to_flip() -> None:
    """A second copy of the switch could be flipped and quietly disagree.

    `parents` and `admin` import the guard, never the value, so the only place
    the freeze can be turned off is `billing`.
    """
    for module in (parents, admin):
        assert not hasattr(module, "BILLING_AND_SUBSCRIPTION_ENABLED"), module.__name__


def test_the_switch_is_off_and_both_switches_agree() -> None:
    """Unfreezing one without the other grants nothing, so they are pinned together."""
    assert billing.BILLING_AND_SUBSCRIPTION_ENABLED is False
    assert entitlement_service.MANUAL_BILLING_OVERRIDE_ENABLED is False


def test_a_manual_override_row_no_longer_grants_paid_access() -> None:
    decision = entitlement_service._billing_decision(  # noqa: SLF001
        billing={"billing_status": "manual_override", "subscription_tier": "family"},
        parent_profile={"subscription_tier": "family"},
        student_tier="free_trial",
        has_active_binding=True,
        paid_grant=None,
    )

    assert decision["effective_plan"] == "free_trial"
    assert decision["source"] == "free_tier"
    assert decision["blocking_reason"] == "billing_frozen"


def test_an_override_does_not_take_away_what_the_student_profile_already_carries() -> None:
    """The freeze removes the bypass, it does not demote an assigned student."""
    decision = entitlement_service._billing_decision(  # noqa: SLF001
        billing={"billing_status": "manual_override", "subscription_tier": "family"},
        parent_profile={"subscription_tier": "family"},
        student_tier="student",
        has_active_binding=True,
        paid_grant=None,
    )

    assert decision["effective_plan"] == "student"
    assert decision["source"] == "student_profile"


def test_the_override_branch_is_still_there_to_unfreeze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Negative control: the behaviour was switched off, not deleted."""
    monkeypatch.setattr(entitlement_service, "MANUAL_BILLING_OVERRIDE_ENABLED", True)

    decision = entitlement_service._billing_decision(  # noqa: SLF001
        billing={"billing_status": "manual_override", "subscription_tier": "family"},
        parent_profile={"subscription_tier": "family"},
        student_tier="free_trial",
        has_active_binding=True,
        paid_grant=None,
    )

    assert decision["effective_plan"] == "family"
    assert decision["source"] == "manual_override"
