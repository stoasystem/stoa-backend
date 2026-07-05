# Phase 249 Plan

## Goal

Make quota state reconcilable and explainable across ledger rows, counters, entitlements, and support summaries.

## Tasks

1. Add explicit no-usage, over-limit, and stale reconciliation signals.
2. Add bounded support actions and explanations to reconciliation output.
3. Propagate support action/explanation to student usage summaries and action summaries.
4. Expose support action/explanation through parent/admin usage response models.
5. Render usage support action/explanation in parent/admin account operations UI.
6. Add focused tests for no-usage, over-limit, support action, and parent summary exposure.
7. Verify backend focused tests, Ruff, and frontend build.

## Success Criteria

- Reconciliation compares ledger rows, aggregate counters, entitlement limits, and account operations usage summaries for a student/action/day.
- Drift, stale, partial, over-limit, no-usage, and matched states are support-safe and test-covered.
- Parent/admin account operations expose remaining quota, reconciliation status, and support action without raw content.
- Repair recommendations are explicit and non-mutating unless a future phase adds a guarded repair action.
