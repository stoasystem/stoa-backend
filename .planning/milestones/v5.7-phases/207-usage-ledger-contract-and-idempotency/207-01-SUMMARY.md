---
phase: 207
plan: 207-01
status: complete
requirements_completed:
  - LEDGER-01
key_files:
  created:
    - src/stoa/db/repositories/usage_ledger_repo.py
    - src/stoa/services/usage_ledger_service.py
    - tests/test_usage_ledger.py
  modified:
    - src/stoa/models/question.py
---

## Summary

Defined and implemented the usage ledger contract for `question_submission` events. The ledger stores deterministic keys, idempotency keys, counter references, entitlement snapshots, and privacy metadata while excluding raw learning content and billing/provider internals.

## Verification

- `uv run pytest tests/test_usage_ledger.py tests/test_questions.py tests/test_entitlements.py tests/test_subscription_operations.py` — 49 passed.
- `uv run ruff check ...` on touched source/tests — passed.
