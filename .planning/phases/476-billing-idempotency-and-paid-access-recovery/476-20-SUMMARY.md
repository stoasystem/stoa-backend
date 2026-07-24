---
phase: 476-billing-idempotency-and-paid-access-recovery
plan: 20
subsystem: payments
tags: [billing, notifications, idempotency, dynamodb, zoneinfo, privacy]

requires:
  - phase: 476-13
    provides: Current explicit beneficiary grants and immutable renewal-grace transitions
provides:
  - Closed masked payment-method projection with monotonic observation versions
  - Zurich month-end-minus-seven-day expiry schedule and persistent Web reminder state
  - Parent-and-beneficiary in-app/email fan-out through durable recipient/channel intents
affects: [billing-lifecycle, notification-delivery, parent-web-billing, phase-476-security-gate]

tech-stack:
  added: []
  patterns:
    - Method-digest plus expiry-month logical identity with monotonic provider observations
    - One private delivery intent per exact account and channel with isolated failure results
    - Verified-and-positively-deliverable email eligibility while preserving in-app delivery

key-files:
  created:
    - src/stoa/services/payment_reminder_service.py
    - tests/test_payment_method_expiry_reminders.py
  modified:
    - src/stoa/services/notification_service.py
    - src/stoa/db/repositories/notification_repo.py

key-decisions:
  - "Bind one logical reminder to the safe payment-method digest and exact expiry year/month, while using a monotonic observation version to reject delayed replacement facts."
  - "Route every account/channel effect through notification_service.register_delivery_intent so recipient failures remain independent and existing delivery CAS semantics own retries."
  - "Require both verified identity and an explicit deliverable email status; invalid, unverified, bounced, suppressed, and unknown addresses remain in-app-only."

patterns-established:
  - "Reminder persistence is parent-fenced private notification state and participates in the existing deletion inventory and tombstone path."
  - "Provider identifiers exist only long enough to derive a domain-separated digest; rows, payloads, results, and operation IDs expose no provider ID or card secret."

requirements-completed: [V9BILL-04]

duration: 12min
completed: 2026-07-24
---

# Phase 476 Plan 20: Payment-Method Expiry Reminder Summary

**Zurich-calendar payment expiry reminders now persist a closed masked method projection and fan out at most once per family recipient/channel through the existing durable delivery CAS.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-24T15:13:26Z
- **Completed:** 2026-07-24T15:24:55Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Added a provider-neutral default-payment-method adapter boundary that immediately projects the raw method into only a digest, brand, last four digits, expiry month/year, source subscription digest, and observation version.
- Computes the reminder at Zurich local midnight exactly seven local calendar days before the card month-end across leap years, variable month lengths, and DST changes.
- Persists owner-fenced `payment_expiry_reminder.v1` Web state, immediately resolves older method observations, refuses stale provider facts, and never reopens a previously resolved method/month.
- Resolves the parent plus every current explicit beneficiary grant, gives every account the same in-app reminder, and adds email only for verified positively deliverable addresses.
- Registers deterministic independent recipient/channel operations through the existing notification delivery-intent CAS, so one failure cannot suppress another account or mutate billing/grant state.

## Task Commits

TDD execution produced the mandatory RED and GREEN gates:

1. **Task 476-20-01 RED: Add failing payment expiry reminder contract** - `df214a8` (test)
2. **Task 476-20-01 GREEN: Deliver idempotent payment expiry reminders** - `a70fa20` (feat)

## Files Created/Modified

- `src/stoa/services/payment_reminder_service.py` - Safe method projection, Zurich scheduling, exact grant/profile recipients, replacement clearing, and isolated delivery orchestration.
- `tests/test_payment_method_expiry_reminders.py` - Leap-year/DST/boundary, deliverability, dedupe, stale observation, replacement, redaction, and failure-isolation proof.
- `src/stoa/services/notification_service.py` - Exact service-level `register_delivery_intent()` boundary for one private recipient/channel effect.
- `src/stoa/db/repositories/notification_repo.py` - Owner-fenced reminder persistence, monotonic state updates, private-row inventory, and deletion coverage.

## Decisions Made

- Used the provider method ID only as an in-memory digest input. The raw provider ID, PAN, CVC, fingerprint, token, and secret-shaped fields never cross into persistence, delivery payloads, responses, or logs.
- Used the existing immutable subscription digest and observation version as reminder authority. A newer observation may resolve an older method; a delayed older observation cannot clear newer state, and a same-version/different-method observation fails closed.
- Kept in-app and email as distinct durable operations under the recipient's permanent account-fence generation. Email eligibility is conservative and does not affect the in-app operation.
- Retained resolved method/month rows so replacing away and later returning to the same method/month cannot create a second logical notification.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Established the planned reminder-to-notification service source link**
- **Found during:** Task 476-20-01 pre-wave verification
- **Issue:** `payment_reminder_service.py` was absent and `notification_service.py` exposed no service-level `register_delivery_intent` boundary, so the required one-intent-per-recipient/channel link could not be source-verified.
- **Fix:** Added a narrow service wrapper over the existing durable delivery CAS and made the reminder service call it once for each exact account/channel operation.
- **Files modified:** `src/stoa/services/notification_service.py`, `src/stoa/services/payment_reminder_service.py`
- **Verification:** Exact source-link selector passes; repeated runs reuse the same five operation IDs and perform no second provider callback.
- **Committed in:** `a70fa20`

**2. [Rule 1 - Bug] Prevented delayed provider observations from clearing newer reminder state**
- **Found during:** Task 476-20-01 GREEN hardening
- **Issue:** Method/month identity alone deduplicated delivery but an older delayed observation could have treated the prior method as current and resolved a newer replacement.
- **Fix:** Compare persisted monotonic observation versions before replacement clearing, ignore stale observations, and reject a same-version/different-method conflict.
- **Files modified:** `src/stoa/services/payment_reminder_service.py`, `tests/test_payment_method_expiry_reminders.py`
- **Verification:** The delayed-observation selector preserves the newer pending reminder while duplicate scheduler/provider runs retain deterministic intent identities.
- **Committed in:** `a70fa20`

---

**Total deviations:** 2 auto-fixed (1 Rule 2 missing critical integration, 1 Rule 1 correctness bug)
**Impact on plan:** Both changes directly enforce the planned trust boundary and idempotency contract. No network endpoint, provider implementation, package, schema migration, billing write, or production operation was added.

## Security Verification

- The safe projection rejects PAN/CVC/fingerprint/token/secret-shaped inputs and persists only the seven approved payment observation fields plus reminder lifecycle metadata.
- Recipient selection starts with the authenticated parent and adds only current exact beneficiary grants whose subscription digest matches the observed subscription.
- Invalid, unverified, bounced, suppressed, and unknown email states produce no email intent; their in-app operation remains present.
- Each deterministic operation binds method/month, exact recipient, and channel, then crosses the existing owner-fenced register/claim/begin/complete delivery state machine.
- Per-recipient exceptions are reduced to the safe `failed` status and do not include provider error text. Other recipient/channel operations continue.
- Billing inputs and grant fixtures remain byte-equivalent after injected delivery failure; the reminder source contains no billing/grant update or provider mutation path.
- Focused verification passes with `16 passed`; the related notification, deletion, delivery-recovery, WebSocket, grant, and transition regression set passes with `95 passed`.
- The later aggregate `scripts/verify_phase476_security_gate.py` is not present yet. This summary records source-bound ASVS L1 evidence without claiming the aggregate phase gate.

## Known Stubs

None introduced. The provider adapter and channel delivery callables are explicit worker integration boundaries exercised only with fixtures in this plan; no mock data or empty rendering state is wired into application output.

## Issues Encountered

- The repository sandbox denied direct `.git/index.lock` creation for the RED commit; the managed approval path created both normal commits with hooks enabled and no verification bypass.
- Ruff's optional formatter would reformat inherited sections of the large notification files, so only the two new files were mechanically formatted. The plan's required Ruff check passes for all four scoped files.
- The aggregate Phase 476 security gate is owned by a later phase plan and remains absent; focused threat selectors and inherited regressions are green.

## User Setup Required

None - no dependency, credential, provider configuration, migration command, deployment, or external service action was added.

## Next Phase Readiness

- A later scheduler/worker can supply the provider adapter and in-app/email effect callables without reimplementing projection, calendar, recipient, persistence, or retry identity rules.
- The parent Web billing projection can read the persistent reminder row and clear it immediately when the provider observation version advances.
- Later Phase 476 plans must include these focused selectors in the aggregate security gate and must keep real provider/production execution separately approved.

## Self-Check: PASSED

- FOUND: `src/stoa/services/payment_reminder_service.py`
- FOUND: `tests/test_payment_method_expiry_reminders.py`
- FOUND: `src/stoa/services/notification_service.py`
- FOUND: `src/stoa/db/repositories/notification_repo.py`
- FOUND: `476-20-SUMMARY.md`
- FOUND: `df214a8`
- FOUND: `a70fa20`
- PASS: focused reminder suite (`16 passed`)
- PASS: related notification/grant/privacy regression (`95 passed`)
- PASS: planned Ruff gate, targeted mypy, and `git diff --check`
- PASS: exact `payment_reminder_service.py` to `notification_service.register_delivery_intent` source link

---
*Phase: 476-billing-idempotency-and-paid-access-recovery*
*Completed: 2026-07-24*
