---
phase: 208
plan: 208-01
status: complete
requirements_completed:
  - LEDGER-02
key_files:
  modified:
    - src/stoa/routers/questions.py
    - tests/test_questions.py
---

## Summary

Question submission now records a durable usage ledger event after the daily quota counter accepts usage. The route supports optional `idempotencyKey` retry handling and keeps existing quota-denial behavior intact.

## Verification

- `uv run pytest tests/test_usage_ledger.py tests/test_questions.py tests/test_entitlements.py tests/test_subscription_operations.py` — 49 passed.
- Ruff on touched source/tests — passed.
