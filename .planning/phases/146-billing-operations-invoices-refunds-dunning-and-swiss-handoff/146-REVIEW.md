---
phase: 146-billing-operations-invoices-refunds-dunning-and-swiss-handoff
reviewed: 2026-06-11T21:51:40Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - src/stoa/services/subscription_service.py
  - src/stoa/routers/parents.py
  - src/stoa/routers/admin.py
  - tests/test_subscription_operations.py
  - .planning/phases/146-billing-operations-invoices-refunds-dunning-and-swiss-handoff/146-BILLING-OPERATIONS-SWISS-HANDOFF-SPEC.md
  - .planning/phases/146-billing-operations-invoices-refunds-dunning-and-swiss-handoff/146-01-PLAN.md
findings:
  critical: 1
  warning: 3
  info: 0
  total: 4
status: remediated
---
# Phase 146: Code Review Report

**Reviewed:** 2026-06-11T21:51:40Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** remediated

## Summary

Reviewed the new invoice/refund/dunning/accounting projection paths, the parent/admin billing response models, and the new accounting export route against the Phase 146 intent. The route wiring is straightforward; the defects are in the new billing projections. Full `pytest tests/test_subscription_operations.py` verification was not possible in this shell because the environment is missing the project import path by default and `python-jose`.

## Remediation

All actionable findings were remediated before Phase 146 completion:

- `CR-01`: provider refund facts are separated from remaining refund eligibility; refund webhooks now update `latestInvoice.amountRefunded`, recompute remaining eligible amount, and preserve refund/accounting references.
- `WR-01`: dunning retry dates are preserved across later webhook events that do not carry a new retry schedule.
- `WR-02`: neutral states now project as `none` or `checkout_pending`, and active recovery from `past_due`/`payment_failed` now projects `recovered`.
- `WR-03`: tests now assert refunded totals, remaining refundable amounts, accounting refund values, retry-date preservation, checkout-pending dunning state, and recovered state.

Post-remediation verification passed locally:

```bash
.venv/bin/python -m pytest tests/test_subscription_operations.py
.venv/bin/ruff check src/stoa/services/subscription_service.py src/stoa/routers/billing.py src/stoa/routers/parents.py src/stoa/routers/admin.py tests/test_subscription_operations.py
```

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: Refund webhooks corrupt refund/accounting amounts after the first provider refund

**Classification:** BLOCKER
**File:** `src/stoa/services/subscription_service.py:1473-1506`, `src/stoa/services/subscription_service.py:1706-1735`
**Issue:** `_refund_from_provider_object()` stores the webhook refund amount as `refund_summary["eligibleAmount"]`, and `_apply_billing_transition()` then persists that summary verbatim. The invoice projection is never updated with the refunded total on `refund.*` / `charge.refunded` events, so partial refunds leave the model internally inconsistent: after a CHF 500 refund on a CHF 1500 invoice, `latestInvoice.amountRefunded` stays `0`, while `refund.eligibleAmount` becomes `500` instead of the remaining refundable `1000`. That breaks both parent/admin refund readiness and the new accounting export.
**Fix:**
```python
# Keep provider refund facts separate from operator eligibility.
refunded_amount = _amount_value(event_object.get("amount") or event_object.get("amount_refunded"), 0) or 0
invoice = dict(updated.get("latest_invoice") or {})
invoice["amountRefunded"] = (invoice.get("amountRefunded") or 0) + refunded_amount
updated["latest_invoice"] = invoice
updated["refund_summary"] = _refund_readiness(updated) | {
    "state": provider_state,
    "providerRefundId": refund_id,
    "updatedAt": now,
}
```

## Warnings

### WR-01: Later webhook events erase the stored dunning retry date

**Classification:** WARNING
**File:** `src/stoa/services/subscription_service.py:1373-1399`, `src/stoa/services/subscription_service.py:1727-1734`
**Issue:** `next_payment_attempt` is only taken from the current webhook payload. When a billing record is already `payment_failed` or `past_due`, any later `refund.*` or `customer.updated` event rebuilds `dunning` with `nextPaymentAttempt=None`, even though the provider retry schedule has not changed. Support loses the retry ETA that Phase 146 explicitly surfaces.
**Fix:**
```python
existing_next_attempt = ((existing.get("dunning") or {}).get("nextPaymentAttempt"))
next_attempt = transition.get("next_payment_attempt") or existing_next_attempt
updated["dunning"] = _dunning_projection(updated, next_payment_attempt=next_attempt)
```

### WR-02: Neutral billing states are projected as `manual_review`, and the required `recovered` state is unreachable

**Classification:** WARNING
**File:** `src/stoa/services/subscription_service.py:1558-1596`
**Issue:** `_dunning_projection()` returns `manual_review` for both `status == "none"` and `status == "checkout_pending"`, so a brand-new account or an ordinary checkout in progress looks like an operational incident in the new API fields. The same state machine also has no way to emit the spec's `recovered` state after a payment retry succeeds (`146-BILLING-OPERATIONS-SWISS-HANDOFF-SPEC.md:37-45`).
**Fix:**
```python
if status == "none":
    state = "none"
elif status == "checkout_pending":
    state = "checkout_pending"
elif status == "active" and previous_status in {"past_due", "payment_failed"}:
    state = "recovered"
```

### WR-03: The new refund tests miss the broken amount and dunning regressions

**Classification:** WARNING
**File:** `tests/test_subscription_operations.py:613-744`
**Issue:** The added webhook coverage only checks that a refund ID appears and that one failed-payment event produces a retry date. It never asserts `latestInvoice.amountRefunded`, remaining refundable amount, accounting-export refund amounts, or that a later webhook preserves `dunning.nextPaymentAttempt`. The blocker above therefore passes the suite unchanged.
**Fix:**
```python
assert refunded_status["latestInvoice"]["amountRefunded"] == 500
assert refunded_status["refund"]["eligibleAmount"] == 1000
assert refunded_status["accountingHandoff"]["refund"]["eligibleAmount"] == 1000

follow_up = webhook_client.post("/billing/webhooks/stripe", ...)
assert parent_client.get("/parents/me/subscription/billing").json()["dunning"]["nextPaymentAttempt"] == expected_retry_at
```

---

_Reviewed: 2026-06-11T21:51:40Z_
_Reviewer: the agent (gsd-code-reviewer)_
_Depth: standard_
