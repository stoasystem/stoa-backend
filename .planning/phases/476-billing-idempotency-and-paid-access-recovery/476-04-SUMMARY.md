---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 04
subsystem: payments
tags: [dynamodb, migration, idempotency, billing-plan, redaction, conditional-write]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Canonical BillingPlanId vocabulary and safe Stripe Price configuration from Plans 01 and 03
provides:
  - Bounded zero-write preview for legacy and canonical plan identities
  - Digest/version-conditioned non-production apply with evidence-bound operator review
  - Redacted source-bound local preview receipt and canonical production-admin defaults
affects: [476-14, 476-29, billing-migration, free-trial-history, account-provisioning]

tech-stack:
  added: []
  patterns:
    - Whole-row and provider-evidence digests bind preview to conditional apply
    - Canonical target validation imports the closed BillingPlanId contract directly
    - Public receipts expose only digests, counts, safe source-plan labels, and dispositions

key-files:
  created:
    - src/stoa/jobs/migrate_billing_plan_identity.py
    - tests/test_plan_identity_migration.py
    - docs/security/phase-476-plan-migration-preview.json
    - .planning/phases/476-billing-idempotency-and-paid-access-recovery/476-USER-SETUP.md
  modified:
    - scripts/provision_production_admin.py

key-decisions:
  - "Validate every migration target through BillingPlanId; canonical current values may pass directly, while legacy paid values require an exact configured sandbox Price/subscription match plus explicit beneficiary evidence."
  - "Permit evidence-bound operator dispositions only for review-required ambiguity; malformed or live-mode evidence blocks apply and cannot be overridden."
  - "Publish local fixture evidence as review_required and apply-blocked, without claiming an approved DynamoDB/Stripe inventory read or running any production/provider mutation."
  - "Preserve all pre-existing AWS SSO operator changes in provision_production_admin.py and commit only the two Phase 476 free_trial default corrections."

patterns-established:
  - "Migration preview/apply: validate closed coordinates and configuration before repository access, hash the complete row and relevant evidence, then re-read before a version-conditioned write."
  - "Migration replay: matching schema, canonical target, and evidence digest proves success without a second write."

requirements-completed: [V9BILL-02, V9BILL-04]

duration: 16min
completed: 2026-07-24
---

# Phase 476 Plan 04: Digest-Bound Plan Identity Migration Summary

**Legacy plan rows can now be classified without guessing and conditionally migrated only from an unchanged, redacted, non-production preview bound to canonical BillingPlanId targets.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-07-24T09:29:26Z
- **Completed:** 2026-07-24T09:45:53Z
- **Tasks:** 1
- **Files modified:** 4 implementation/evidence files

## Accomplishments

- Added a bounded preview/apply job with closed coordinate and input schemas, zero-write preview, canonical/exact-match/review/malformed classifications, and direct `BillingPlanId` target validation.
- Bound apply to the whole preview, configuration, source SHA, full row, relevant provider/beneficiary/trial evidence, row version, and any required operator disposition.
- Refused production environments and live provider evidence, blocked malformed evidence from override, skipped changed rows, and made committed replay zero-write.
- Added DynamoDB strong-read/conditional-write support plus exact prior migration-field history for controlled rollback without copying provider identifiers into receipts.
- Added default-preview CLI, explicit apply and verify modes, a closed Lambda entrypoint, and pre-repository rejection of unknown fields and coordinates.
- Changed only the Cognito/profile bootstrap fallback values in the protected production-admin script from `free` to `free_trial`, preserving every pre-existing AWS SSO operator edit.
- Published a local-fixture receipt bound to GREEN source `ccdf1eb5fc05b6e1d504e29358490ea88e1a9616`; it reports one unresolved legacy `standard` row, zero writes, and `applyBlocked: true`.

## Task Commits

TDD execution produced the required RED and GREEN commits, followed by one source-bound evidence publication:

1. **Task 476-04-01 RED: Add failing plan identity migration contract** - `d4371f6` (test)
2. **Task 476-04-01 GREEN: Implement digest-bound plan identity migration** - `ccdf1eb` (feat)
3. **Task 476-04-01 Evidence: Publish redacted migration preview** - `3f005fd` (docs)

## Files Created/Modified

- `src/stoa/jobs/migrate_billing_plan_identity.py` - Preview/apply contracts, classifications, digest integrity, conditional repository adapter, receipt verifier, Lambda handler, and CLI.
- `tests/test_plan_identity_migration.py` - Zero-write, ambiguity, missing trial, live refusal, wrong digest, changed evidence, operator review, replay, redaction, Lambda, and CLI proof.
- `docs/security/phase-476-plan-migration-preview.json` - Redacted local dry-run receipt that remains review-required and apply-blocked.
- `scripts/provision_production_admin.py` - Canonical `free_trial` Cognito and DynamoDB bootstrap defaults only.
- `.planning/phases/476-billing-idempotency-and-paid-access-recovery/476-USER-SETUP.md` - Human prerequisites for a later approved non-production inventory preview.

## Decisions Made

- Canonical values are parsed through `BillingPlanId`; no hidden alias map can become active runtime plan identity.
- Legacy `standard`, `premium`, and `tutor_supported` rows select a paid target only from an exact configured test Price/subscription plus explicit beneficiary evidence.
- Legacy/free-trial rows without trustworthy historical first-activation evidence remain review-required and never default the trial start to the current time.
- Apply preflights every required operator disposition before rereading or writing, then reports changed evidence per row and retains conditional-write replay safety.
- The checked receipt intentionally proves the local safe boundary rather than fabricating unavailable sandbox inventory evidence.

## Deviations from Plan

None - the implementation followed the requested local/dry execution boundary. The plan’s external approved-inventory preview remains explicitly gated in `476-USER-SETUP.md`; no live or production evidence was synthesized.

## Security Verification

- `BillingPlanId` is imported directly from `src/stoa/models/billing.py`, establishing the previously absent source/model key link.
- Preview has no write path and all 30 focused/adjacent tests observe zero writes for canonical, ambiguous, malformed, missing-trial, and live-evidence cases.
- Apply rejects wrong preview digests, tampered candidates, production environments, live provider evidence, absent/mismatched operator dispositions, and changed row/evidence versions.
- Exact Price classification requires a non-live subscription reference and explicit one-beneficiary or one-to-three-family scope; child count is never inferred.
- Receipt schema verification rejects private coordinate, email, customer, Price, subscription, beneficiary, secret, and card/CVC fields or identifier-shaped values.
- The source contains no Stripe create/update/modify call, Cognito mutation, checkout mutation, or unbounded scan.
- The aggregate `scripts/verify_phase476_security_gate.py` is not present yet and remains owned by a later Phase 476 plan; this summary makes no aggregate phase-gate claim.

## Known Stubs

None introduced. Empty collections in the implementation are bounded accumulators or test zero-effect assertions, not UI/data-source placeholders.

## Issues Encountered

- The repository sandbox initially denied `.git/index.lock`; the exact files were staged through the managed approval path and normal hooks ran.
- `scripts/provision_production_admin.py` already contained user-owned AWS SSO changes. Interactive patch staging committed only the two canonical plan defaults; the user hunks remain byte-for-byte in the working tree and were never staged or reverted.
- The approved DynamoDB/Stripe sandbox inventory was intentionally not accessed under the user’s local-only execution constraint. The checked receipt uses one deterministic unresolved local fixture and cannot authorize apply.

## User Setup Required

External read authority is required only for the later real non-production inventory run. See `476-USER-SETUP.md` for:

- Approved `STOA_BILLING_MIGRATION_ENVIRONMENT`
- Restricted Stripe sandbox/test read key
- Exact non-production DynamoDB/Stripe read approval
- Evidence-bound review dispositions before apply

## Next Phase Readiness

- Plan 476-14 can consume the explicit missing/contradictory historical trial classification and keep new free usage denied until evidence exists.
- Plan 476-29 can require a later approved receipt and reject this local fixture as real sandbox closure evidence.
- No production apply, live Stripe object mutation, Cognito provisioning, or real data migration was run.

## Self-Check: PASSED

- FOUND: `src/stoa/jobs/migrate_billing_plan_identity.py`
- FOUND: `tests/test_plan_identity_migration.py`
- FOUND: `docs/security/phase-476-plan-migration-preview.json`
- FOUND: `scripts/provision_production_admin.py`
- FOUND: `d4371f6`
- FOUND: `ccdf1eb`
- FOUND: `3f005fd`
- PASS: focused and adjacent verification (`30 passed`)
- PASS: Ruff on all planned implementation/test files
- PASS: preview receipt schema/redaction verifier (`status=review_required`)
- PASS: direct `BillingPlanId` source/model key link
- PASS: provider/Cognito mutation scan and `git diff --check`
- PASS: protected admin script cached commit contained exactly the two canonical default hunks

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
