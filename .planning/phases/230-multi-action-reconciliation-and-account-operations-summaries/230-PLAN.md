---
phase: 230
name: Multi-Action Reconciliation And Account Operations Summaries
status: planned
---

# Phase 230 Plan: Multi-Action Reconciliation And Account Operations Summaries

## Goal

Extend reconciliation and usage summaries so parent/admin support views can explain all governed usage actions while preserving question quota compatibility.

## Tasks

1. Add generic counter reading and action reconciliation.
2. Extend `build_student_usage_summary` with `actions`, `groups`, and `totals`.
3. Preserve existing question top-level fields.
4. Extend parent/admin response models for additive multi-action fields.
5. Extend admin event/reconciliation routes with action selection.
6. Add focused tests for mixed-action summaries and contract preservation.

## Verification

- `.venv/bin/python -m pytest tests/test_usage_ledger.py tests/test_subscription_operations.py -q`
- `.venv/bin/python -m ruff check src/stoa/db/repositories/usage_ledger_repo.py src/stoa/services/usage_ledger_service.py src/stoa/routers/admin.py src/stoa/routers/parents.py tests/test_usage_ledger.py`
