# Phase 254 Context

## Milestone

v5.16 End-To-End Product Readiness And Release Evidence

## Requirement

SMOKE-01 Backend Product Smoke Evidence

## Starting Point

Phase 253 closed the focused frontend e2e gate. Phase 254 verifies that backend release-support surfaces expose enough support-safe status metadata for triage without adding raw private data or pretending external providers are locally complete.

## Files Reviewed

- `src/stoa/services/core_smoke_service.py`
- `src/stoa/services/usage_ledger_service.py`
- `src/stoa/services/subscription_service.py`
- `src/stoa/services/account_operations_service.py`
- `src/stoa/services/curriculum_service.py`
- `src/stoa/services/curriculum_ops_service.py`
- `src/stoa/services/curriculum_migration_service.py`
- `src/stoa/services/curriculum_analytics_service.py`
- `src/stoa/routers/admin.py`
- `src/stoa/routers/parents.py`
- `src/stoa/routers/auth.py`
- `src/stoa/routers/practice.py`
- `src/stoa/routers/questions.py`
- `src/stoa/routers/conversations.py`
- focused backend tests listed in `254-VERIFICATION.md`

## Evidence Expectations

- `GET /admin/core-smoke` returns a bounded readiness matrix.
- Account operations combine verification, billing, child binding, entitlement, and usage support state.
- Billing support evidence exposes lifecycle, invoice, refund, provider readiness, and reconciliation state without leaking provider secrets.
- Usage reconciliation exposes support-safe status, support action, drift, and explanation.
- Curriculum readiness is covered by rollout, operations, migration, and analytics tests.
