---
phase: 145-production-checkout-webhook-and-twint-capable-stripe-gating
reviewed: 2026-06-11T21:39:15Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - src/stoa/services/subscription_service.py
  - src/stoa/routers/parents.py
  - src/stoa/routers/admin.py
  - src/stoa/config.py
  - tests/test_subscription_operations.py
  - pyproject.toml
  - requirements.txt
findings:
  critical: 2
  warning: 4
  info: 0
  total: 6
status: remediated
---
# Phase 145: Code Review Report

**Reviewed:** 2026-06-11T21:39:15Z
**Depth:** standard
**Files Reviewed:** 7
**Status:** remediated

## Summary

Reviewed the Stripe gating, webhook, TWINT, provider-lookup, and billing response changes in the scoped files. The main defects are in webhook state transitions: the implementation grants or revokes subscription access off Checkout Session events that are not authoritative for subscription entitlement, and several new metadata/reporting paths can now return misleading or forgeable state.

The scoped test file exercises the happy paths added in this phase, but it does not cover the failure modes below. I also could not run the test module end-to-end in this shell because the local environment is missing runtime dependencies (`python-jose` during collection).

## Remediation

All actionable findings were remediated before Phase 145 completion:

- `CR-01`: `checkout.session.completed` now leaves billing in `checkout_pending`; paid entitlement is activated by `invoice.paid` or subscription status events.
- `CR-02`: replacement checkout sessions preserve prior billing status/tier so `checkout.session.expired` cannot downgrade an already-active subscription.
- `WR-01`: billing responses default to persisted readiness/TWINT state for existing rows.
- `WR-02`: selected `paymentMethodType` is derived only from selected payment method details, not from offered Checkout methods.
- `WR-03`: provider lookup fallback now paginates scans.
- `WR-04`: unsigned webhooks require explicit `stripe_allow_unsigned_test_webhooks=true`; the default rejects unsigned payloads.

Post-remediation verification passed locally:

```bash
.venv/bin/python -m pytest tests/test_subscription_operations.py
.venv/bin/ruff check src/stoa/config.py src/stoa/services/subscription_service.py src/stoa/routers/parents.py src/stoa/routers/admin.py tests/test_subscription_operations.py
```

## Narrative Findings (AI reviewer)

## Critical Issues

### CR-01: `checkout.session.completed` upgrades access before payment is actually confirmed

**Classification:** BLOCKER  
**File:** `src/stoa/services/subscription_service.py:1307-1308,1405-1408,1485-1490`  
**Issue:** The webhook transition logic turns every `checkout.session.completed` event into `billing_status="active"` and immediately updates the parent profile tier. For subscription Checkout flows, especially asynchronous methods like TWINT, completing the session is not the same as a successful paid subscription. This can grant paid access before the invoice/payment actually succeeds, and the later `invoice.payment_failed` event only partially repairs the mistake after entitlements were already issued.  
**Fix:**
```python
if event_type == "checkout.session.completed":
    status = existing.get("billing_status") or "checkout_pending"

if event_type in {"invoice.paid", "customer.subscription.updated"}:
    status = authoritative_subscription_status(...)
```

### CR-02: An expired replacement checkout downgrades an already-paid parent to free

**Classification:** BLOCKER  
**File:** `src/stoa/services/subscription_service.py:1309-1310,1407-1408,1485-1490`  
**Issue:** `checkout.session.expired` is mapped straight to `billing_status="canceled"`, and canceled status forces `subscription_tier="free"` on the user profile. If an already-active parent opens an upgrade/downgrade checkout and lets it expire, this code locally cancels the existing subscription even though the underlying Stripe subscription is still active.  
**Fix:**
```python
elif event_type == "checkout.session.expired":
    if existing.get("billing_status") == "checkout_pending":
        status = "canceled"
    else:
        status = existing.get("billing_status") or "provider_unknown"
```

## Warnings

### WR-01: Billing endpoints now report current environment readiness instead of the stored record state

**Classification:** WARNING  
**File:** `src/stoa/services/subscription_service.py:816-832,859-870`, `src/stoa/routers/parents.py:656,687`, `src/stoa/routers/admin.py:734-751`  
**Issue:** `_billing_response()` now recomputes `readiness` and `twint` from the current process settings whenever routers pass `settings`. That overrides the values persisted on the billing row. A historical test checkout can therefore come back as `mode="test"` and `providerLivemode=false` while also reporting `readiness.state="live_enabled"`, which is contradictory and changes the API semantics for existing consumers.  
**Fix:** Keep the persisted row as the default billing response source, and expose current configuration in a separate field such as `environmentReadiness` if operators need both views.

### WR-02: `paymentMethodType` is derived from allowed methods, not the method the customer actually used

**Classification:** WARNING  
**File:** `src/stoa/services/subscription_service.py:1044-1046,1077-1080,1342-1345`  
**Issue:** The code stores `payment_method_types[0]` as `paymentMethodType`. On a live TWINT-capable Checkout Session, that list is the set of offered methods (`["card", "twint"]` in the added test), not the selected one. In practice this will mislabel TWINT payments as `card` whenever card appears first.  
**Fix:**
```python
def _payment_method_type_from_provider_object(event_object: dict[str, Any]) -> str | None:
    details = event_object.get("payment_method_details") or {}
    return details.get("type")
```
Populate the field only from charge/payment-intent/invoice objects that carry the actual method used.

### WR-03: The provider-lookup fallback only scans one DynamoDB page

**Classification:** WARNING  
**File:** `src/stoa/services/subscription_service.py:1230-1252`  
**Issue:** When a lookup row is missing, `_find_parent_id_for_provider_object()` falls back to a single `scan()` call with no `LastEvaluatedKey` loop. That matters immediately for migrated billing rows, because this phase introduces lookup rows but does not backfill old records. Once the table spans multiple pages, legitimate webhooks for older subscriptions can fail with `Unable to resolve parent for provider event` depending on which page the row lands on.  
**Fix:** Page through the scan until a match is found, or backfill/query a dedicated lookup/index before relying on the fallback path.

### WR-04: Unsigned webhook bodies are still accepted on any non-`production` deployment

**Classification:** WARNING  
**File:** `src/stoa/services/subscription_service.py:1170-1184`, `src/stoa/config.py:93-102`  
**Issue:** Signature verification is skipped whenever `stripe_webhook_secret` is empty and `environment` is anything other than `production|prod`. That means a public `staging`, `preview`, or misconfigured environment can accept forged webhook JSON that mutates billing state and parent subscription tiers. This is an authentication bypass on every non-prod deployment unless operators remember to set the secret anyway.  
**Fix:** Require webhook signature verification by default and allow unsigned events only behind an explicit local/test-only flag, e.g. `allow_unsigned_test_webhooks=False`.

---

_Reviewed: 2026-06-11T21:39:15Z_  
_Reviewer: the agent (gsd-code-reviewer)_  
_Depth: standard_
