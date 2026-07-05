# Phase 253 Plan

## Goal

Close the focused frontend e2e release gate for auth, account operations, billing/subscription, and curriculum.

## Tasks

1. Confirm frontend worktree state and release-critical e2e specs.
2. Run the Phase 252 focused e2e command.
3. If execution is blocked, classify the blocker and resolve it if safe.
4. If specs fail, classify each failure as product regression, frontend/API contract mismatch, fixture/platform issue, external blocker, or test precision issue.
5. Fix real test precision issues without changing application behavior.
6. Rerun the same focused e2e command and record pass/fail evidence.
7. Commit the frontend test fix and backend phase evidence separately.

## Success Criteria

- The focused command runs against Playwright's configured test server.
- The final run records timestamp, command, and pass/fail count.
- Any changes are limited to release-gate correctness.
- The v5.14 focused frontend e2e blocker is closed or carried forward with precise classification.
