---
phase: 209
plan: 209-01
status: complete
requirements_completed:
  - RECON-01
key_files:
  modified:
    - src/stoa/db/repositories/usage_ledger_repo.py
    - src/stoa/services/usage_ledger_service.py
    - src/stoa/routers/admin.py
    - tests/test_usage_ledger.py
---

## Summary

Added reconciliation that compares daily question counter rows with usage ledger totals. Admins can preview reconciliation and optionally repair counter-missing/count-mismatch states.

## Verification

- `uv run pytest tests/test_usage_ledger.py tests/test_questions.py tests/test_entitlements.py tests/test_subscription_operations.py` — 49 passed.
- Ruff on touched source/tests — passed.
