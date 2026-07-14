---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 01
subsystem: security
tags: [authorization, identity, safe-errors, client-recovery, pytest, jwks]

requires:
  - phase: full-project-audit
    provides: SEC-001, SEC-002, and SEC-004 reproductions and release-blocker evidence
provides:
  - Immutable canonical Actor and typed authorization contracts
  - Stable safe security errors, redacted events, and HTTP taxonomy
  - Exhaustive generated client error-action and retry contract
  - Offline provider/repository doubles and collectible Wave 0 security matrices
affects: [472-02, 472-03, 472-04, 472-05, 472-06, 472-07, 472-08, 472-09, 472-10, 478]

tech-stack:
  added: []
  patterns: [immutable Actor, fail-closed typed policy input, allowlisted telemetry, deterministic generated contract, injected offline doubles]

key-files:
  created:
    - src/stoa/security/errors.py
    - src/stoa/security/identity.py
    - src/stoa/security/authorization.py
    - src/stoa/security/events.py
    - src/stoa/security/client_error_actions.py
    - docs/security/client-error-actions.json
    - tests/security/conftest.py
    - tests/test_student_authorization_matrix.py
  modified:
    - tests/test_identity_authorization.py
    - tests/test_auth_security.py
    - tests/test_teacher_onboarding.py

key-decisions:
  - "Canonical security roles are a closed student|parent|teacher|admin enum; legacy values are rejected rather than normalized."
  - "Public security responses are limited to code, message, and correlationId; Retry-After is valid only for bounded temporary dependency failures."
  - "Phase 472 owns the generated client recovery contract while Phase 478 owns rendering and application integration."

patterns-established:
  - "Fail-closed contracts: every authorization input declares resource type, action, purpose, and a resolver."
  - "Safe projection: events and client errors are constructed from allowlists, never filtered from serialized provider payloads."
  - "Wave 0 isolation: clocks, provider calls, repositories, JWKS transport, and keys are injected without ambient AWS or network access."

requirements-completed: [V9AUTH-01, V9AUTH-02, V9AUTH-03, V9AUTH-04, V9AUTH-05, V9ACCESS-01, V9ACCESS-02, V9ACCESS-03]

duration: 7 min
completed: 2026-07-14
---

# Phase 472 Plan 01: Security contracts and Wave 0 verification harness Summary

**A fail-closed identity/authorization vocabulary, safe error and event boundary, exhaustive client recovery contract, and 77-case offline Wave 0 collection now anchor the remaining Phase 472 implementation plans.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-14T19:31:00Z
- **Completed:** 2026-07-14T19:38:07Z
- **Tasks:** 4
- **Files modified:** 18

## Accomplishments

- Defined immutable single-role Actors, active-only authorization state, typed resource/action/purpose policy inputs, stable 401/403/404/409/503 errors, and allowlisted redacted security events.
- Generated a byte-stable client action contract covering every security error, one-refresh token recovery, explicit 409 actions, no 403/404 retry, and bounded 503 retry behavior for idempotent reads only.
- Added injected clocks, two isolated RSA/JWKS keysets, async transport and Cognito recorders, missing/outage/timeout repositories, canaries, and builders with no live credentials or network.
- Added 77 collectible Wave 0 tests with SEC-001 zero-mutation reproductions, positive/negative route families, hidden-resource indistinguishability, inventory mutation, reconciliation tightening, and the canonical terminology gate.

## Task Commits

Each task was committed atomically:

| Task | Description | Commit |
| --- | --- | --- |
| 472-01-01 | Security contracts and safe errors/events | `9a3d1ce` |
| 472-01-02 | Safe client error actions and generated contract | `389fc0a` |
| 472-01-03 | Offline security test fixtures | `0096f14` |
| 472-01-04 | Wave 0 security matrices and red contracts | `1dce405` |

## Files Created/Modified

- `src/stoa/security/` — canonical identity, authorization, error, event, and client recovery contracts.
- `scripts/generate_client_error_actions.py` — deterministic contract generator.
- `docs/security/client-error-actions.json` — versioned machine-readable web/mobile recovery contract.
- `tests/security/conftest.py` — offline clock, JWKS, provider, repository, builder, and canary fixtures.
- `tests/test_*authorization*.py` and focused security modules — implemented contract assertions plus named red surfaces for Plans 02–10.

## Decisions Made

- Kept `teacher` as the sole canonical teacher role and confined the historical term to exact negative/reconciliation fixtures.
- Modeled non-active Actors for lifecycle/reconciliation evidence, while making `can_authorize` true only for `active` accounts.
- Kept the reference client interpreter framework-independent so Phase 478 can consume the generated contract without importing backend transport or policy internals.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Moved deterministic JSON rendering into the importable security module**

- **Found during:** Task 2 (safe client error actions)
- **Issue:** The repository's `scripts/` directory is not a Python package, so importing the generator directly from pytest failed collection.
- **Fix:** Made `render_client_error_actions()` part of `stoa.security.client_error_actions`; the CLI script delegates to it and tests exercise the same function.
- **Files modified:** `src/stoa/security/client_error_actions.py`, `scripts/generate_client_error_actions.py`, `tests/test_client_error_actions.py`
- **Verification:** 16 implemented contract tests pass and regeneration produces a byte-for-byte clean artifact.
- **Committed in:** `389fc0a`

---

**Total deviations:** 1 auto-fixed (1 blocking issue).
**Impact on plan:** The fix preserves one canonical generator and adds no dependency or scope expansion.

## Issues Encountered

- The system `pytest` executable did not load the editable `src/stoa` package; all verified commands use the repository's locked `.venv/bin/pytest`, which collects and runs offline successfully.
- Future-plan behavior is intentionally red and was collected rather than executed, exactly as Wave 0 requires. No assertion was skipped or xfailed.

## User Setup Required

None - no external service configuration required.

## Verification

- `pytest ... -k 'contract or safe_error or security_event or actor or retry or client_action'`: **16 passed, 5 deselected**.
- Client contract regeneration: **byte-for-byte clean**.
- All eight Wave 0 modules: **77 tests collected** with no live Cognito/AWS evidence claimed.
- Ruff and `git diff --check`: **passed**.

## Next Phase Readiness

- Ready for `472-02`: token verification and explicit identity resolution can implement against the stable Actor/error/JWKS test contracts.
- Plans 02–10 must turn the named red surfaces green without weakening them; the phase itself is not complete.

## Self-Check: PASSED

- Key created files exist on disk.
- Four atomic task commits are present.
- Every task acceptance gate and the plan-level verification command passed at its intended Wave 0 scope.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-14*
