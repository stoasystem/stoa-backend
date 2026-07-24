---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 09
subsystem: payments
tags: [stripe, checkout, reconciliation, fastapi, authorization, redaction]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Durable checkout commands, safe supersession, retrieval-only reconciliation, and closed support projection from Plans 05-08
provides:
  - Owner-concealed parent checkout status, recheck, and explicit-confirmation supersession APIs
  - Capability-gated admin checkout support and same-command recheck APIs
  - Closed parent outcomes and suffix-only admin provider identity
  - Retrieval-only bounded Stripe test Session adapter with no create or expire authority
affects: [476-11, 476-23, checkout-result, admin-billing-support, web-billing]

tech-stack:
  added: []
  patterns:
    - Resolve the opaque checkout reference under exact parent ownership before reconciliation
    - Reuse one retrieval-only reconciliation primitive for parent and admin support APIs
    - Keep admin provider identity suffix-only and request bodies structurally closed

key-files:
  created:
    - tests/test_billing_recheck_apis.py
  modified:
    - src/stoa/routers/parents.py
    - src/stoa/routers/admin.py
    - src/stoa/security/admin_authorization.py
    - tests/test_admin_authorization.py
    - docs/security/route-authorization-inventory.json

key-decisions:
  - "Parent status and recheck first resolve the opaque reference with the authenticated parent ID, then pass only that same reference and owner to retrieval-only reconciliation."
  - "Admin checkout read and recheck both require billing_operations_reader and a parent coordinate; neither route receives payment-success or provider-mutation authority."
  - "Parent outcomes are exactly confirming, active, not_completed, or support_needed; only not_completed permits a new checkout."
  - "The Stripe adapter performs bounded list/retrieve reads only, rejects malformed key evidence, and projects provider Session identity as a six-character suffix for admins."

patterns-established:
  - "Closed billing API: empty extra-forbid recheck bodies, literal-true supersession confirmation, and allowlisted response models."
  - "Support authorization precedes checkout repository/provider effects; wrong-capability admins and non-parent actors stop at the dependency boundary."

requirements-completed: [V9BILL-02, V9BILL-04]

duration: 10min
completed: 2026-07-24
---

# Phase 476 Plan 09: Owner-Safe Billing Recheck APIs Summary

**Parents and billing-support admins can now inspect and reconcile one original checkout command through closed, owner/capability-authorized APIs without gaining payment-creation or manual-success authority.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-24T12:14:07Z
- **Completed:** 2026-07-24T12:24:21Z
- **Tasks:** 1
- **Files modified:** 6

## Accomplishments

- Added the five planned routes: parent status, parent recheck, confirmed parent supersession, admin support read, and admin recheck.
- Added exact parent ownership lookup before every parent repository/provider path; another parent's real reference and a random reference return the same concealed response.
- Mapped public parent state to exactly `confirming`, `active`, `not_completed`, or `support_needed`, with new checkout allowed only after terminal nonpayment.
- Wired parent and admin rechecks to `billing_reconciliation_service.reconcile_checkout_command()` with a retrieval-only provider dependency.
- Added literal `confirmed=true` supersession with the Plan 07 service and closed plan/beneficiary input; callback and unknown fields are rejected.
- Added a closed admin projection containing parent, target plan, beneficiaries, timestamps, lifecycle state, stable failure code/action, lease generation, and only a six-character Session suffix.
- Classified both admin routes under `billing_operations_reader` and refreshed the executable checked authorization inventory.

## Task Commits

TDD execution produced the required RED and GREEN commits:

1. **Task 476-09-01 RED: Add failing billing recheck API contract** - `86aa58f` (test)
2. **Task 476-09-01 GREEN: Expose safe billing recheck APIs** - `6b36c85` (feat)

## Files Created/Modified

- `tests/test_billing_recheck_apis.py` - Ownership concealment, role/capability denial, closed schemas, recheck/supersession, redaction, OpenAPI, and no-manual-success proof.
- `src/stoa/routers/parents.py` - Parent status/recheck/supersession models and routes plus bounded retrieval-only Stripe evidence adapter.
- `src/stoa/routers/admin.py` - Closed support/recheck models, capability-gated routes, reconciliation call, and suffix-only projection.
- `src/stoa/security/admin_authorization.py` - Exact `billing_operations_reader` classification for both new admin routes.
- `tests/test_admin_authorization.py` - Updated exact registered-admin route cardinality after adding two routes.
- `docs/security/route-authorization-inventory.json` - Regenerated checked runtime/OpenAPI authorization projection.

## Decisions Made

- Parent GET and POST recheck use the same owner-authorized command and same reconciliation primitive; neither accepts plan, beneficiary, callback, provider, or payment-success input.
- Admin read/recheck requires the existing billing support reader capability. A wrong billing capability is denied before command lookup or provider access.
- Admin routes require the parent coordinate in the query so the existing owner-bound repository lookup remains the only command resolver; the returned command is still checked against that owner before reconciliation.
- Stripe Session discovery is bounded to 100 test-mode read results and then retrieves the exact matching opaque reference with expanded price evidence. Missing or malformed evidence remains support-needed rather than becoming payment success.
- Checkout completion continues to map to confirming. Only a pre-existing authoritative activation record can produce `active`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Registered new admin routes in executable authorization policy**
- **Found during:** Task 476-09-01 GREEN verification
- **Issue:** Adding `/admin/billing/checkouts/...` without an exact classifier would make the routes fail closed as unclassified and leave the checked authorization inventory stale.
- **Fix:** Added an exact `billing_operations_reader`/read policy for both routes and regenerated the deterministic inventory.
- **Files modified:** `src/stoa/security/admin_authorization.py`, `docs/security/route-authorization-inventory.json`
- **Verification:** Route inventory and runtime/OpenAPI checked JSON match; unauthorized admin effects remain zero.
- **Committed in:** `6b36c85`

**2. [Rule 1 - Bug] Updated exact admin route cardinality**
- **Found during:** Task 476-09-01 adjacent authorization verification
- **Issue:** The complete-route regression still expected 111 routes after the two planned admin routes were registered.
- **Fix:** Updated the exact count to 113 while retaining uniqueness and policy checks for every route.
- **Files modified:** `tests/test_admin_authorization.py`
- **Verification:** Extended authorization/reconciliation/supersession aggregate passes (`214 passed`).
- **Committed in:** `6b36c85`

---

**Total deviations:** 2 auto-fixed (1 missing critical authorization artifact, 1 direct regression).
**Impact:** Both changes are required for the planned routes to remain executable, fully classified, and source-bound; no unrelated production behavior changed.

## Security Verification

- Parent ownership is checked through `get_checkout_command_by_public_ref(checkout_ref, parent_id=actor.user_id)` before reconciliation or provider access.
- Foreign-real and random references return the same 404 response; students stop at the parent Actor dependency before repository/provider effects.
- Both admin routes require `billing_operations_reader`; `billing_refund_executor` cannot read or recheck a command.
- Recheck request models are empty and `extra="forbid"`; supersession accepts only literal confirmation, one paid plan, bounded beneficiaries, and the idempotency header.
- The route provider exposes `find_checkout_session()` and `retrieve_checkout_session()` only. There is no create, expire, payment, refund, or manual-success method.
- Parent outcomes are closed and admin output omits full Session IDs/URLs, provider keys, secrets, provider exceptions, and private account canaries.
- OpenAPI contains all five routes and no manual-paid/mark-success operation.
- All T-476-09-H focused mitigations have observed passing selectors. No unresolved ASVS L1 High threat remains in this plan's source boundary.
- The aggregate `scripts/verify_phase476_security_gate.py` is not present yet and remains owned by a later plan; this summary does not overclaim aggregate phase closure.
- No real Stripe request, customer charge, credential use, deployment, or production operation occurred; all API behavior used deterministic mocks.

## Verification

- Exact plan command: `37 passed` across `tests/test_billing_recheck_apis.py` and `tests/test_route_authorization_inventory.py`.
- Extended admin authorization, reconciliation, and supersession regression: `214 passed`.
- Ruff passes on all planned files plus the directly updated authorization files.
- `git diff --check` passes.
- Source scan confirms `parents.py` calls `billing_reconciliation_service.reconcile_checkout_command()` and no manual-paid/success route exists.

## Known Stubs

None introduced. Empty collections in tests and existing routers are bounded accumulators or response defaults, not unwired application data.

## Issues Encountered

- Context7 was unavailable locally. Current Stripe Session list/retrieve and line-item expansion semantics were checked against Stripe's official API reference.
- The aggregate Phase 476 security gate script is not present yet, so focused and adjacent source-bound verification was used without claiming the later aggregate gate.
- Git metadata writes required the managed approval path; normal hooks remained enabled and no verification was bypassed.

## User Setup Required

None for this plan. Existing Stripe sandbox configuration remains necessary for a separately approved external test, but no provider or production action was performed here.

## Next Phase Readiness

- Plan 476-11 can preserve confirming status until signed invoice-paid and active-subscription facts record authoritative activation.
- Plan 476-23 and Web result/support views can consume the four closed parent outcomes and suffix-only admin support projection.
- The later aggregate Phase 476 gate must include the ownership, capability, no-create, closed-schema, redaction, and no-manual-success selectors added here.

## TDD Gate Compliance

- RED: `86aa58f` failed all eight focused API contract tests before route implementation.
- GREEN: `6b36c85` passes the focused plan gate and adjacent authorization/reconciliation regressions.

## Self-Check: PASSED

- FOUND: `src/stoa/routers/parents.py`
- FOUND: `src/stoa/routers/admin.py`
- FOUND: `src/stoa/security/admin_authorization.py`
- FOUND: `tests/test_billing_recheck_apis.py`
- FOUND: `tests/test_admin_authorization.py`
- FOUND: `docs/security/route-authorization-inventory.json`
- FOUND: `476-09-SUMMARY.md`
- FOUND: `86aa58f`
- FOUND: `6b36c85`
- PASS: exact plan verification (`37 passed`)
- PASS: extended verification (`214 passed`)
- PASS: Ruff and `git diff --check`
- PASS: `parents.py` → `billing_reconciliation_service.reconcile_checkout_command()` key link

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
