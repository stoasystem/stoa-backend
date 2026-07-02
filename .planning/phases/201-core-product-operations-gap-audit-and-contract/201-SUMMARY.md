# Phase 201 Summary: Core Product Operations Gap Audit And Contract

**Date:** 2026-07-02
**Status:** Complete

## Completed

- Audited current auth, registration, login, forgot/reset, subscription, billing, quota, usage, parent, and admin behavior from code.
- Documented current reality in `201-CURRENT-REALITY-AUDIT.md`.
- Reordered v5.6 from broad core-ops planning into concrete implementation phases:
  - Phase 202: effective entitlements and paid access enforcement.
  - Phase 203: usage ledger and quota reconciliation.
  - Phase 204: email verification and login-code policy.
  - Phase 205: customer/admin visibility and release gate.
- Added `201-NEXT-DEVELOPMENT-TASKS.md` as the implementation task queue.
- Updated roadmap, requirements, state, milestone, project, and stoa_docs gap docs.

## Key Findings

- Registration currently marks Cognito email as verified and profile email status as `admin_marked_verified`; real email verification lifecycle is missing.
- Login is password-only Cognito auth; login-code behavior is absent.
- Stripe billing activation updates parent profile tier, but question quota reads the student's own `subscription_tier`.
- Usage is currently counter-based, not a durable event ledger with entitlement source and admin query dimensions.
- Parent/admin billing views exist, but complete entitlement + usage + verification visibility is still missing.

## Next

Proceed to Phase 202: implement effective entitlement resolver and paid access enforcement for linked students.
