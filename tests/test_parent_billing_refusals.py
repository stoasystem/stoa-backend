"""A parent's checkout lookup refuses with billing codes, not hand-written bodies (#274)."""

from __future__ import annotations

import pytest

from stoa.routers import parents
from stoa.rule_violation import RuleViolation
from stoa.services.billing_errors import BillingErrorCode


def _lookup_raising(monkeypatch: pytest.MonkeyPatch, error: Exception) -> None:
    def lookup(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(
        parents.checkout_command_repo, "get_checkout_command_by_public_ref", lookup
    )


@pytest.mark.parametrize(
    ("error", "code", "status"),
    [
        (ValueError("not a checkout ref"), BillingErrorCode.CHECKOUT_NOT_FOUND, 404),
        (RuntimeError("throttled"), BillingErrorCode.CHECKOUT_TEMPORARILY_UNAVAILABLE, 503),
    ],
)
def test_a_checkout_lookup_refuses_by_code(monkeypatch, error, code, status):
    _lookup_raising(monkeypatch, error)

    with pytest.raises(RuleViolation) as refused:
        parents._load_owned_checkout_command("chk_unknown", parent_id="parent-a")

    assert refused.value.code is code
    assert refused.value.status_code == status
