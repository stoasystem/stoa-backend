---
phase: 473-student-content-privacy-and-practice-integrity
plan: 01
subsystem: security-contracts
tags: [pydantic, attachments, privacy, practice, structured-errors, entitlements]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    provides: Verified Actor ownership, redacted structured errors, and one-role authorization vocabulary
provides:
  - Closed opaque upload and attachment lifecycle contracts
  - Exhaustive redacted attachment error and client-action registry
  - Tier-authoritative 5 GiB/15 GiB attachment storage limits
  - Answer-free practice preview and directional-hint schemas
  - Recorded-attempt result and explicit privileged-answer schemas
  - Adversarial ownership, redaction, schema, and recursive leak fixtures
affects: [473-02, 473-03, 473-04, 473-05, 473-06, 473-07, 478-mobile]

tech-stack:
  added: []
  patterns:
    - Pydantic extra-forbid allowlists with external camel-case aliases
    - Exhaustive enum-to-status-message-action registries
    - Durable attempt receipt required before answer-bearing result construction

key-files:
  created:
    - src/stoa/models/attachment.py
    - src/stoa/security/attachment_errors.py
    - src/stoa/models/practice.py
    - tests/test_attachment_security.py
    - tests/test_practice_privacy.py
  modified:
    - src/stoa/config.py
    - src/stoa/services/entitlement_service.py

key-decisions:
  - "Public attachment contracts expose only opaque upload/attachment IDs and safe metadata; storage coordinates and extracted content are structurally absent."
  - "Only upload_service_unavailable is retryable, with bounded idempotent semantics; every attachment error has one stable client action."
  - "Answer-bearing practice results require a non-empty durable attempt receipt, while previews and hints use separate extra-forbid allowlists."

patterns-established:
  - "Attachment boundary: client-selected ownership and storage fields fail validation before service code."
  - "Practice boundary: previews cannot acquire answer-derived fields without failing schema and recursive canary tests."

requirements-completed: [V9PRIV-01, V9PRIV-02, V9PRIV-03]

duration: 9 min
completed: 2026-07-16
---

# Phase 473 Plan 01: Security contracts and Wave 0 privacy fixtures Summary

**Opaque attachment lifecycles, exhaustive safe recovery errors, authoritative storage allowances, and attempt-gated practice answer schemas now form executable privacy contracts.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-07-16T10:02:00Z
- **Completed:** 2026-07-16T10:11:32Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Defined strict upload intent, saved attachment, quota, lifecycle, and safe metadata models without public bucket, key, owner, OCR, or extracted-content fields.
- Added an exhaustive eight-code attachment error registry with safe public bodies and bounded client recovery behavior.
- Added structural answer-free preview/hint models and answer-bearing result/privileged models, including a durable-attempt receipt gate.
- Seeded Wave 0 adversarial fixtures for foreign ownership, provider/key/OCR redaction, entitlement tiers, nested answer leakage, OpenAPI drift, and failed attempt persistence.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define upload, attachment, quota and safe-error contracts** - `fce6839` (feat)
2. **Task 2: Define answer-free preview and answer-bearing result schemas** - `a7d0186` (feat)

## Files Created/Modified

- `src/stoa/config.py` - Central upload, validation, and attachment storage bounds.
- `src/stoa/services/entitlement_service.py` - Effective-plan attachment storage projection.
- `src/stoa/models/attachment.py` - Opaque upload/attachment request and response allowlists.
- `src/stoa/security/attachment_errors.py` - Exhaustive safe attachment error and recovery contract.
- `src/stoa/models/practice.py` - Answer-free preview/hint and attempt-gated answer schemas.
- `tests/test_attachment_security.py` - Ownership, quota, registry, and redaction adversarial fixtures.
- `tests/test_practice_privacy.py` - Schema, OpenAPI, persistence sentinel, and recursive leak fixtures.

## Decisions Made

- Public attachment schemas use opaque IDs and safe metadata only; storage/provider coordinates remain private by construction.
- Free entitlement receives 5 GiB and standard/premium receive 15 GiB from the authoritative effective-plan projection.
- Missing and foreign uploads share one `upload_not_found` public projection; sensitive diagnostic inputs are ignored.
- A practice answer result can only be built from a non-empty recorded-attempt receipt; privileged pre-attempt answers remain a separate explicit schema.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The first sandboxed Task 2 commit attempt could not create `.git/index.lock`; rerunning the same scoped commit with approved repository write access succeeded and hooks were not bypassed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plans 473-02 through 473-07 can import the stable attachment, error, preview, hint, result, and privileged-answer contracts.
- Integration risk remains intentionally open: existing routers still need migration to these models in the later Phase 473 plans.

## Verification

- `tests/test_attachment_security.py tests/test_practice_privacy.py tests/test_entitlements.py tests/test_client_error_actions.py`: 53 passed.
- Combined practice/curriculum regression: 29 passed.
- Generated attachment and preview schema privacy invariants: PASS.
- `git diff --check`: PASS.

## Self-Check: PASSED

- All five created key files exist.
- Both task commits are present in repository history.
- All task acceptance criteria and plan-level verification commands pass.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-16*
