---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 08
subsystem: payments
tags: [stripe, checkout, reconciliation, idempotency, leases, redaction]

requires:
  - phase: 476-billing-idempotency-and-paid-access-recovery
    provides: Durable checkout command, owner lookup, provider lease, conditional Session attachment, and command-first sandbox checkout from Plans 05 and 06
provides:
  - Retrieval-only recovery of one original owner-authorized checkout command
  - Exact sandbox Session identity validation and lease-fenced local attachment
  - Honest support-needed handling for provider ambiguity and local repair failures
  - Closed suffix-only billing support projection
affects: [476-11, 476-23, checkout-result, admin-billing-support, billing-reconciliation]

tech-stack:
  added: []
  patterns:
    - Retrieval-only provider capability for financial rechecks
    - Owner lookup before provider access and exact command evidence before attachment
    - Closed internal reconciliation result followed by an allowlisted support projection

key-files:
  created:
    - src/stoa/services/billing_reconciliation_service.py
    - tests/test_billing_reconciliation.py
  modified: []

key-decisions:
  - "A recheck receives only provider find/retrieve capabilities; Session creation is structurally absent and the original command's persisted reference and provider-key digest are its only lookup inputs."
  - "Reconciliation reuses the checkout repository's versioned claim and conditional attachment so an expired lease can recover while an active or stale lease cannot double mutate."
  - "Complete browser checkout evidence remains confirming rather than active; only an already recorded authoritative activation produces the active support state."
  - "Support output is a closed allowlist with lifecycle, timestamp, safe action, failure class, lease generation, and a six-character provider suffix."

patterns-established:
  - "Same-command recovery: owner-authorized lookup, fenced claim, retrieval-only provider read, exact sandbox evidence validation, conditional attachment, closed classification."
  - "Ambiguity preservation: timeouts, absent proof, malformed evidence, and attachment uncertainty remain support-needed or retryable and never become nonpayment or activation."

requirements-completed: [V9BILL-02]

duration: 7min
completed: 2026-07-24
---

# Phase 476 Plan 08: Same-Command Billing Reconciliation Summary

**Original checkout commands now recover exact Stripe sandbox Sessions through a retrieval-only, lease-fenced path and expose only a closed redacted support state.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-24T11:07:35Z
- **Completed:** 2026-07-24T11:14:52Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Added `reconcile_checkout_command()` with owner-authorized command lookup before provider access, bounded lease takeover, exact provider evidence matching, and conditional same-command Session attachment.
- Added a provider protocol containing only `find_checkout_session()` and `retrieve_checkout_session()`; no provider-create function, Stripe SDK, HTTP client, credential, or live mutation exists in the service.
- Classified attached open, complete, expired, canceled, activation-recorded, unavailable, and malformed evidence without treating browser return or Checkout completion as paid activation.
- Preserved timeout, missing proof, mismatch, contention, and local attachment ambiguity as support-needed or retryable while retaining the original command identity.
- Added deterministic failure injection before command read, after command claim/before provider read, after provider read/before attachment, and after attachment/before response.
- Added a closed support projection containing only lifecycle state, last recheck timestamp, safe action, failure class, lease generation, and a six-character provider Session suffix.

## Task Commits

TDD execution produced the required RED and GREEN commits:

1. **Task 476-08-01 RED: Add failing billing reconciliation contract** - `32fcc8d` (test)
2. **Task 476-08-01 GREEN: Reconcile original checkout command** - `fd1949a` (feat)

## Files Created/Modified

- `src/stoa/services/billing_reconciliation_service.py` - Retrieval-only reconciliation, exact sandbox evidence checks, lease-bound conditional repair, closed outcomes, and redacted support projection.
- `tests/test_billing_reconciliation.py` - Required partial-failure, timeout, contention, takeover, mismatch, terminal-state, no-create, replay, and redaction matrix.

## Decisions Made

- Reused `claim_provider_create()` only as the existing versioned persistence lease; reconciliation never receives or calls the provider Session-create capability.
- Required both the authenticated owner lookup and the opaque command reference in provider client/metadata evidence, plus exact stored customer when available, Price, environment, test Session identity, and Stripe-hosted URL.
- Classified provider `complete` as confirming because paid access still requires the later signed invoice-paid plus active-subscription activation proof.
- Kept exception details out of durable/public results and mapped every dependency or evidence failure to a closed failure code.

## Deviations from Plan

None - plan executed exactly as written.

## Security Verification

- The previously absent `billing_reconciliation_service.py` to `checkout_command_repo.py` key link now calls owner lookup, versioned claim, conditional Session attachment, and ambiguity persistence.
- A fail-if-create provider sentinel proves the recheck never calls its deliberately hostile create method; the provider protocol itself exposes only find and retrieve.
- Cross-owner lookup returns not found before any provider access.
- Foreign reference, metadata, customer, Price, environment, live-mode, and live-ID evidence cannot attach.
- An active lease makes zero provider calls; an expired lease takes over once; repeated recheck retrieves and replays one attached command.
- Provider timeout, absent proof, and malformed retrieval remain support-needed rather than terminal nonpayment.
- Checkout `complete` remains confirming and does not activate access; only a pre-existing `activation_recorded` command returns active without provider access.
- The support projection excludes parent, command, checkout reference, provider-key digest, full Session ID/URL, Price, customer, secret, PII, and provider exception canaries.
- All T-476-08-H mitigations have observed named passing selectors in the focused source-bound suite. No unresolved ASVS L1 High threat remains in this plan's source boundary.
- The aggregate `scripts/verify_phase476_security_gate.py` is not present yet and remains owned by a later Phase 476 plan; this summary makes no aggregate phase-gate claim.
- No real provider call, charge, credential use, deployment, or production operation occurred; all provider behavior used deterministic in-process mocks.

## Verification

- Exact plan command: `PYTHONPATH=. .venv/bin/pytest -q tests/test_billing_reconciliation.py` (`25 passed`).
- Exact lint command: `.venv/bin/ruff check src/stoa/services/billing_reconciliation_service.py tests/test_billing_reconciliation.py` (passed).
- Adjacent checkout repository, checkout command, supersession, billing fact, and reconciliation regression: `76 passed`.
- Targeted mypy: no issues in `billing_reconciliation_service.py`.
- Source scans confirm all planned repository links and no Session-create, provider SDK, or HTTP-client dependency.
- `git diff --check` passed.

## Known Stubs

None introduced. Optional values and empty collections are bounded internal result/test-double state, not unwired application data.

## Issues Encountered

- The repository sandbox denied direct `.git/index.lock` creation. Both commits used the managed approval path with normal hooks enabled; no verification was bypassed.
- The aggregate Phase 476 security gate is not present yet, so focused and adjacent source-bound suites were used without overclaiming phase completion.

## User Setup Required

None for this plan. Existing Stripe sandbox configuration will be needed by later approved integration work, but this plan performed no external provider access.

## Next Phase Readiness

- Checkout result and support routes can call the same-command recovery primitive without receiving provider-create authority.
- Later webhook/activation work can keep Checkout completion as confirming until signed paid-invoice and active-subscription facts atomically activate access.
- The later aggregate Phase 476 gate must include this plan's no-create, mismatch, contention, ambiguity, replay, and redaction selectors.

## Self-Check: PASSED

- FOUND: `src/stoa/services/billing_reconciliation_service.py`
- FOUND: `tests/test_billing_reconciliation.py`
- FOUND: `476-08-SUMMARY.md`
- FOUND: `32fcc8d`
- FOUND: `fd1949a`
- PASS: exact focused verification (`25 passed`)
- PASS: Ruff on both planned files
- PASS: summary and source diff checks

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
