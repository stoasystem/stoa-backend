# Phase 201 Summary: Core Product Operations Gap Audit And Contract

**Date:** 2026-07-02
**Status:** Complete

## Completed

- Audited current auth, registration, login, forgot/reset, subscription, billing, quota, usage, parent, and admin behavior from code.
- Documented current reality in `201-CURRENT-REALITY-AUDIT.md`.
- Reordered the remaining final-polish work from one broad core-ops plan into complete feature milestones:
  - v5.6: effective entitlements and paid access enforcement.
  - v5.7: usage ledger and quota reconciliation.
  - v5.8: email verification and login-code policy.
  - v5.9: parent/admin operations visibility.
- Added `201-NEXT-DEVELOPMENT-TASKS.md` as the milestone queue.
- Updated roadmap, requirements, state, milestone, project, and stoa_docs gap docs.

## Key Findings

- Registration currently marks Cognito email as verified and profile email status as `admin_marked_verified`; real email verification lifecycle is missing.
- Login is password-only Cognito auth; login-code behavior is absent.
- Stripe billing activation updates parent profile tier, but question quota reads the student's own `subscription_tier`.
- Usage is currently counter-based, not a durable event ledger with entitlement source and admin query dimensions.
- Parent/admin billing views exist, but complete entitlement + usage + verification visibility is still missing.

## Next

Proceed to v5.6 Phase 202: define entitlement contract and access policy, then implement effective entitlement resolver and paid access enforcement for linked students through phases 203-206.
