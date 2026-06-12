---
phase: 157
plan: 01
subsystem: payments
tags:
  - stripe
  - twint
  - readiness
key-files:
  - src/stoa/config.py
  - src/stoa/services/subscription_service.py
  - src/stoa/routers/admin.py
  - tests/test_subscription_operations.py
metrics:
  tests: "PYTHONPATH=src .venv/bin/pytest tests/test_subscription_operations.py"
---

# Summary 157-01: Live Provider Readiness API Checks

## Delivered

- Added `stripe_webhook_endpoint_url` readiness configuration.
- Added read-only Stripe provider lookup seams for account capability and price metadata.
- Added `get_provider_readiness(settings)` with redacted credential, price, TWINT, webhook, refund, finance, rollout, blocker, and warning sections.
- Added admin endpoint `GET /admin/subscriptions/billing/provider-readiness`.
- Added focused tests for missing production config, test-key refusal, TWINT pending capability, provider API failure redaction, and live readiness success.

## Safety Boundary

- No provider mutation was added.
- Readiness uses only account and price retrieval seams.
- Checkout creation behavior remains unchanged.
- Refund mutation remains disabled and deferred to Phase 158.

## Verification

- `PYTHONPATH=src .venv/bin/pytest tests/test_subscription_operations.py` - passed, 22 tests.
- `PYTHONPATH=src .venv/bin/ruff check src/stoa/config.py src/stoa/services/subscription_service.py src/stoa/routers/admin.py tests/test_subscription_operations.py` - passed.
- `git diff --check` - passed.

## Self-Check

PASSED. PAYACT-02 readiness states are covered without exposing secrets or creating live charges.
