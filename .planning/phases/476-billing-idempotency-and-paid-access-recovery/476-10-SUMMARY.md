---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 10
subsystem: payments
tags: [dynamodb, stripe, idempotency, facts, transactions, leases]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Closed BillingFact/BillingFactKind contracts and durable checkout command/version identity from Plans 01 and 05
provides:
  - Redacted provider event inbox with event-ID and semantic-object deduplication
  - Independently monotonic invoice/subscription object facts and bounded reconciliation leases
  - Provider/plan/version-conditioned atomic paid activation with one absent receipt
affects: [476-06, 476-08, 476-11, billing-webhooks, paid-entitlements, reconciliation]

tech-stack:
  added: []
  patterns:
    - Event receipt and semantic side-effect identity are separate durable records
    - Provider object facts advance by their own object version rather than one global event clock
    - Exact-once activation publishes command, billing, explicit grants, allowance, and receipt in one transaction

key-files:
  created:
    - src/stoa/db/repositories/billing_fact_repo.py
    - tests/test_billing_fact_repo.py
  modified: []

key-decisions:
  - "Persist only domain-separated provider identifier digests, safe fact type/version/timestamp fields, and processing outcomes; rebuild closed BillingFact verification flags rather than storing payload or signature material."
  - "Keep one current fact per command, fact kind, and provider-object digest, advancing it only when that object's version increases."
  - "Require sandbox mode, paid invoice plus active subscription facts, exact command customer/Price/environment/plan/version bindings, unique projection targets, and an absent activation receipt in one transaction."

patterns-established:
  - "Fact-oriented convergence: invoice and subscription delivery order and equal timestamps do not affect the resulting current fact set."
  - "Atomic paid publication: any command condition, target-version condition, or receipt condition loss cancels every activation write."

requirements-completed: [V9BILL-02, V9BILL-04]

duration: 27min
completed: 2026-07-24
---

# Phase 476 Plan 10: Fact-Oriented Billing Activation Summary

**Redacted Stripe event receipts now converge unordered invoice/subscription facts into one provider-bound, version-fenced DynamoDB activation transaction with an exact-once receipt.**

## Performance

- **Duration:** 27 min
- **Started:** 2026-07-24T08:33:22Z
- **Completed:** 2026-07-24T09:00:34Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Added distinct `billing_event_inbox.v1` and `billing_semantic_dedupe.v1` records so repeated Event IDs and different Event IDs for the same type/object retain safe audit evidence without repeating side effects.
- Added `billing_object_fact.v1` persistence linked directly to `BillingFact` and `BillingFactKind`; each object fact advances monotonically without consulting unrelated event timestamps.
- Added a bounded, generation-fenced reconciliation lease for missing/current-object recovery.
- Added one activation transaction conditioned on command version, customer digest, Price, environment, plan, plan version, sandbox mode, current invoice/subscription facts, unique targets, monotonic projection versions, and absent `billing_activation_receipt.v1`.
- Proved event/semantic replay, equal timestamps, delayed older snapshots, both invoice/subscription orders, lease takeover, mismatch/live refusal, redaction, transaction shape, and injected all-or-nothing failure.

## Task Commits

TDD execution produced the required RED and GREEN commits:

1. **Task 476-10-01 RED: Add failing billing fact repository contract** - `10413cd` (test)
2. **Task 476-10-01 GREEN: Persist billing facts and atomic activation** - `7c3ae7c` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/billing_fact_repo.py` - Redacted event/semantic registration, monotonic object facts, strong activation-fact loading, reconciliation lease, and exact-once paid activation.
- `tests/test_billing_fact_repo.py` - Duplicate/order/CAS/lease/redaction/mismatch/live/transaction-failure security matrix.

## Decisions Made

- Raw provider Event and object IDs are converted immediately into domain-separated SHA-256 digests; fact rows contain no raw request, signature, card, CVC, secret, or checkout URL fields.
- Semantic dedupe uses `(event.type, data.object.id)` identity independently of the Event ID receipt so a second delivery can be audited while its repeated side effect is suppressed.
- Invoice and subscription facts use separate provider-object keys and versions; a delayed snapshot can never overwrite a newer version, while equal timestamps for different facts remain valid.
- The activation caller supplies explicit grant items, but every billing/grant/allowance item must carry the same parent, paid plan, plan version, allowance version, and activation version.
- A transaction response loss is classified only through a strong receipt/command reread; absence of proof remains retryable and never authorizes a second activation.

## Deviations from Plan

None - plan executed exactly as written.

## Security Verification

- Event-ID duplicate, semantic duplicate, equal timestamp, reverse delivery order, and delayed older-object selectors pass.
- `last_provider_event_at` and `event.created` global ordering are absent from the repository.
- `BillingFact` and `BillingFactKind` are imported by the repository, establishing the previously missing source-to-model key link.
- Every activation operation has a unique PK/SK target; the command condition binds version/customer/Price/environment/plan/version and the receipt is create-only.
- An injected transaction failure leaves the command, billing projection, grants, allowance, and receipt unchanged.
- Fact-row field allowlisting and private-canary scans prove payload, signature material, card/CVC, secret, and checkout URL fields are not persisted.
- Production/live activation is rejected before persistence; no provider library, provider client, network request, real charge, or production mutation exists in this repository.
- All T-476-10-H mitigations have observed passing selectors in the focused source-bound suite. No unresolved ASVS L1 High threat remains in this plan's files.
- The aggregate `scripts/verify_phase476_security_gate.py` is not present yet and remains owned by a later Phase 476 plan; this summary makes no aggregate phase-gate claim.

## Known Stubs

None introduced.

## Issues Encountered

- Context7 was not installed in the environment, so current DynamoDB transaction behavior was checked against official AWS documentation before implementation.
- Pre-GREEN review caught an incorrect map-valued update shape for advancing facts; it was replaced with a conditional full-item `Put` before the feature commit and final verification.
- Git metadata writes required the managed approval path; normal hooks remained enabled and no verification was bypassed.

## User Setup Required

None - no dependencies, credentials, provider calls, charges, deployment, or production operations were introduced.

## Next Phase Readiness

- Signed webhook orchestration can call `register_provider_event()` and `record_provider_fact()` in either provider delivery order, then load current facts for reconciliation.
- Later orchestration can use the bounded lease to retrieve missing provider objects and call `commit_paid_activation()` only when the full sandbox invoice/subscription predicate is satisfied.
- Later Phase 476 work must add the aggregate source-bound security gate before phase-level completion is claimed.

## Self-Check: PASSED

- FOUND: `src/stoa/db/repositories/billing_fact_repo.py`
- FOUND: `tests/test_billing_fact_repo.py`
- FOUND: `10413cd`
- FOUND: `7c3ae7c`
- PASS: `PYTHONPATH=. .venv/bin/pytest -q tests/test_billing_fact_repo.py` (`10 passed`)
- PASS: focused plus adjacent billing repository/contracts verification (`108 passed`)
- PASS: `.venv/bin/ruff check src/stoa/db/repositories/billing_fact_repo.py tests/test_billing_fact_repo.py`
- PASS: source/model key-link, global-order absence, unique-target, redaction, sandbox, and injected atomic-failure selectors

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
