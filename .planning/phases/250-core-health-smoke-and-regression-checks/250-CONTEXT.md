# Phase 250 Context

## Milestone

v5.15 Usage, Quota, And Product Stability

## Requirement

HEALTH-01 Core Health And Smoke Gates

## Inputs From Phase 249

Usage/quota reconciliation can now explain matched, no-usage, ledger-only, drifted, stale, and over-limit states. Phase 250 adds a deterministic release-gate smoke matrix so local verification can separate route regressions from expected auth/provider/resource blockers.

## Files Changed

- `src/stoa/services/core_smoke_service.py`
- `src/stoa/routers/admin.py`
- `tests/test_core_smoke.py`

## Scope

The smoke matrix is a local readiness contract. It does not call live Cognito, AI, payment, notification, support, or external provider services.
