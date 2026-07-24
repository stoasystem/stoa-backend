---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 03
subsystem: payments
tags: [pydantic-settings, stripe, plan-identity, free-trial, storage]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Canonical BillingPlanId contract and exact checkout-origin policy from Plans 01-02
provides:
  - Byte-identical four-plan SubscriptionTier and BillingPlanId vocabularies
  - Distinct paid Stripe Price settings with non-production live-mode refusal
  - Free-trial account defaults and locked 14-day/5 GB/15 GB configuration
affects: [476-04, 476-06, 476-12, 476-14, billing, entitlements, account-provisioning]

tech-stack:
  added: []
  patterns:
    - Semantic AST inventory distinguishes active persisted identity from legacy daily-counter names
    - Settings fail closed on partial or duplicate paid Price configuration
    - Non-production configuration refuses live Stripe keys and charge enablement

key-files:
  created:
    - tests/test_plan_identity_contract.py
  modified:
    - src/stoa/models/user.py
    - src/stoa/config.py
    - src/stoa/routers/auth.py
    - .env.example

key-decisions:
  - "Use exactly free_trial, student, teacher_supported, and family in SubscriptionTier, with no legacy enum aliases."
  - "Treat any configured Stripe API key or paid Price ID as checkout configuration and require all three paid Price IDs to be nonempty and distinct."
  - "Lock the trial and storage contract at 14 days, 5 GB free, and 15 GB paid while rejecting live keys and live-charge mode outside production."

patterns-established:
  - "Plan identity closure: enum values, Price setting names, typed defaults, Cognito attributes, and persisted profile writes agree exactly."
  - "Secret-free examples: sandbox credential and Price variable names are documented with empty values and live charges false."

requirements-completed: [V9BILL-01, V9BILL-04]

duration: 8min
completed: 2026-07-24
---

# Phase 476 Plan 03: Canonical Plan Identity and Safe Configuration Summary

**Account creation and Settings now share the exact four Web product identities, three distinct paid test Price slots, immutable free-trial/storage limits, and non-production live-charge refusal.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-24T08:02:06Z
- **Completed:** 2026-07-24T08:09:58Z
- **Tasks:** 1
- **Files modified:** 5

## Accomplishments

- Replaced the hidden `free|standard|premium` subscription enum with the exact `free_trial|student|teacher_supported|family` contract already used by `BillingPlanId`.
- Made typed profiles, public student/parent registration, and the Cognito subscription attribute start at `free_trial`.
- Replaced two legacy Price settings with explicit student, teacher-supported, and family Price IDs and rejected missing/duplicate checkout configuration.
- Locked free-trial duration and attachment capacity at 14 days, 5 GB free, and 15 GB paid.
- Refused `sk_live_` keys and live-charge enablement in development/test configuration while keeping the default charge gate false.
- Added 13 source-bound tests covering enum/Settings closure, real registration fixtures, AST write inventory, live-mode refusal, and secret-free environment documentation.

## Task Commits

TDD execution produced the required RED and GREEN commits:

1. **Task 476-03-01 RED: Add failing plan identity contract** - `589ea45` (test)
2. **Task 476-03-01 GREEN: Establish canonical plan identity settings** - `1bd1af6` (feat)
3. **Post-completion fix: Migrate existing runtime tier references** - `d1265ba` (fix)

## Files Created/Modified

- `tests/test_plan_identity_contract.py` - Canonical enum, Settings, AST write, registration, charge-mode, and environment-example gate.
- `src/stoa/models/user.py` - Exact four-plan `SubscriptionTier` plus the typed `free_trial` profile default.
- `src/stoa/config.py` - Three paid Price settings, locked trial/storage values, distinct-price validation, and non-production live-mode refusal.
- `src/stoa/routers/auth.py` - Cognito and persisted public-account defaults now write `free_trial`.
- `.env.example` - Empty sandbox credential/Price names, charge gate false, and explicit trial/storage contract values.

## Decisions Made

- Active plan identity is closed rather than compatibility-mapped: no `FREE`, `STANDARD`, `PREMIUM`, or tutor alias remains on `SubscriptionTier`.
- Checkout configuration becomes subject to completeness validation as soon as either an API key or any paid Price ID is present.
- Production retains its pre-existing activation controls, but development and test settings cannot accept a live key or enable live charging.
- Legacy daily request-count setting names remain outside the new product identity inventory; they are not relabeled as the Phase 476 allowance contract.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Allowed a completely unconfigured local Stripe setup**
- **Found during:** Task 476-03-01 GREEN verification
- **Issue:** The first distinct-Price validator treated the three intentionally empty defaults as duplicate IDs and prevented application/test Settings from loading.
- **Fix:** Applied duplicate detection only after checkout configuration is present; an empty local setup remains safe, while partial and duplicate configured Prices still fail closed.
- **Files modified:** `src/stoa/config.py`
- **Verification:** All 13 focused selectors pass, including empty defaults, missing Prices, and duplicate Prices.
- **Committed in:** `1bd1af6`

---

**Total deviations:** 1 auto-fixed bug.
**Impact on plan:** The fix preserves the intended sandbox-safe default without weakening configured checkout validation.

## Security Verification

- Enum and model-field inventories contain exactly the four canonical product values and three paid Price identities.
- Student and parent registration fixtures observe `free_trial` in both persisted profiles and Cognito custom attributes.
- Partial and duplicate paid Price mappings fail Settings validation.
- Development/test settings reject both `sk_live_` and `stripe_live_charges_enabled=True`; defaults remain disabled.
- `.env.example` contains empty credential/Price values, no live secret prefix, and no sample production Price.
- The source-bound T-476-03-H selectors all pass. The aggregate `scripts/verify_phase476_security_gate.py` is not present yet and remains owned by a later Phase 476 plan; no aggregate phase-gate claim is made here.

## Known Stubs

None introduced.

## Issues Encountered

- Removing forbidden enum aliases initially exposed legacy runtime references in entitlement, subscription, attachment, usage, question, and conversation paths. The user chose immediate correction: `d1265ba` migrated those references to canonical IDs, retained the old daily counters only as a temporary canonical-keyed compatibility mechanism, and restored complete test collection without implementing future grant, allowance, or trial-lifecycle capabilities.

## User Setup Required

- Supply the three Stripe sandbox Price IDs and sandbox credentials outside source control when checkout is configured.
- No credentials, provider calls, charges, deployment, or production mutation were used for this plan.

## Next Phase Readiness

- Plan 476-04 can inventory and migrate persisted legacy identities against one canonical source vocabulary.
- Checkout-command plans can bind student, teacher-supported, and family Prices without a standard/premium translation layer.
- Plans 476-12 and 476-14 retain ownership of explicit paid grants and immutable trial-lifecycle behavior; broad application imports and test collection no longer depend on those future capabilities.

## Self-Check: PASSED

- FOUND: `src/stoa/models/user.py`
- FOUND: `src/stoa/config.py`
- FOUND: `src/stoa/routers/auth.py`
- FOUND: `.env.example`
- FOUND: `tests/test_plan_identity_contract.py`
- FOUND: `589ea45`
- FOUND: `1bd1af6`
- FOUND: `d1265ba`
- PASS: `PYTHONPATH=. .venv/bin/pytest -q tests/test_plan_identity_contract.py tests/test_entitlements.py` (`19 passed`)
- PASS: `.venv/bin/ruff check src/stoa/models/user.py src/stoa/config.py src/stoa/routers/auth.py tests/test_plan_identity_contract.py`
- PASS: `PYTHONPATH=. .venv/bin/pytest --collect-only -q` (`2805 tests collected`)
- PASS: FastAPI application import (`234 routes`)
- PASS: active key link includes `FREE_TRIAL|TEACHER_SUPPORTED` and all three canonical paid Price fields.
- PASS: environment example secret-prefix scan.

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
