# Phase 250 Plan

## Goal

Add deterministic local smoke checks for product flows most likely to break access or support decisions.

## Tasks

1. Define a support-safe core product smoke matrix.
2. Cover service health, login, entitlement, curriculum read, question submit, teacher help, and admin account operations.
3. Classify expected auth/provider/resource blockers separately from regressions.
4. Expose the smoke matrix through an admin-only route.
5. Add focused tests for route coverage, blocker classification, and privacy.
6. Run focused backend tests and Ruff.

## Success Criteria

- Smoke checks cover login, entitlement resolution, curriculum read, question submit, teacher help, and admin/account support.
- Checks separate service availability from product-flow readiness and return route/status/request metadata.
- Expected auth/provider/external blocks are classified separately from regressions.
- Smoke behavior has focused tests and release-gate documentation.
