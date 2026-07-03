---
phase: 210
plan: 210-01
status: complete
requirements_completed:
  - USAGE-01
key_files:
  modified:
    - src/stoa/routers/parents.py
    - src/stoa/routers/admin.py
    - src/stoa/services/usage_ledger_service.py
    - tests/test_usage_ledger.py
---

## Summary

Added privacy-safe parent and admin usage surfaces. Parent child usage summaries and admin support endpoints expose quota usage and reconciliation status without raw question content, private artifact keys, or provider payloads.

## Verification

- `uv run pytest tests/test_usage_ledger.py tests/test_questions.py tests/test_entitlements.py tests/test_subscription_operations.py` — 49 passed.
- Ruff on touched source/tests — passed.
