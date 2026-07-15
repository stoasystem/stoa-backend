---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 11
subsystem: auth
tags: [cognito, jwt, identity-binding, dynamodb, authorization]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    provides: verified access tokens, canonical Actor resolution, and public-role registration barrier
provides:
  - Immutable resumable student/parent registration commands keyed by normalized-email digest
  - Retry-safe issuer-subject bindings with exact reverse-inventory repair
  - Token-bound login and refresh profile resolution through verified Actor.user_id
affects: [phase-474-testing, phase-475-transactions, public-auth, account-recovery]

tech-stack:
  added: []
  patterns: [deny-first identity convergence, immutable command fingerprint, verified-subject response selection]

key-files:
  created:
    - src/stoa/db/repositories/public_identity_repo.py
    - src/stoa/services/public_identity_service.py
    - tests/test_public_identity_lifecycle.py
  modified:
    - src/stoa/db/repositories/identity_repo.py
    - src/stoa/routers/auth.py
    - tests/test_auth_account_lifecycle.py
    - tests/test_auth_security.py

key-decisions:
  - "Use the provider Cognito sub as the stable public user ID and bind it under exactly one configured issuer."
  - "Keep every public profile pending until provider confirmation, canonical group, binding, and verification state all converge."
  - "Build login and refresh responses only after verifying the just-issued access token and resolving Actor.user_id."

patterns-established:
  - "Public identity retries may only complete missing steps; they cannot change issuer, subject, user, role, or registration command."
  - "An interrupted authoritative binding write may reconstruct only its exact matching reverse inventory row."

requirements-completed: [V9AUTH-04]

duration: 30 min
completed: 2026-07-15
---

# Phase 472 Plan 11: Canonical Public Identity Registration and Token-Bound Login Summary

**Student and parent accounts now converge through one immutable Cognito-sub binding, while login and refresh select profiles only from a cryptographically verified access-token subject.**

## Performance

- **Duration:** 30 min
- **Started:** 2026-07-15T12:09:26Z
- **Completed:** 2026-07-15T12:39:49Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Added durable public identity commands with immutable issuer/subject/user/role fingerprints and conditional step advancement.
- Made authoritative identity bindings retry-safe when reverse-inventory creation is interrupted, without permitting re-pointing.
- Wired registration and confirmation into deny-first profile, group, binding, and verification convergence for exact `student|parent` roles.
- Replaced email-based login selection and the empty refresh profile with verified-token, canonical-Actor profile resolution.
- Added offline positive, conflict, replay, partial-failure, duplicate-email, subject-mismatch, and revoked-state proofs.

## Task Commits

Each task was committed atomically:

1. **Task 1: Durable resumable public identity command** - `bb923ca` (feat)
2. **Task 2: Subject-bound registration and confirmation convergence** - `2546be1` (feat)
3. **Task 3: Verified-subject login and refresh response** - `408ce80` (fix)

## Files Created/Modified

- `src/stoa/db/repositories/public_identity_repo.py` - Immutable public identity command storage and conditional convergence transitions.
- `src/stoa/services/public_identity_service.py` - Registration, confirmation, provider lookup, and verified-token orchestration.
- `tests/test_public_identity_lifecycle.py` - Offline end-to-end and mutation-canary identity lifecycle coverage.
- `src/stoa/db/repositories/identity_repo.py` - Exact reverse-inventory repair for an existing authoritative binding.
- `src/stoa/routers/auth.py` - Subject-bound register, confirm, login, and refresh routes.
- `tests/test_auth_account_lifecycle.py` - Updated route lifecycle fixtures for the command-first boundary.
- `tests/test_auth_security.py` - Public confirmation zero-mutation checks at the new command boundary.

## Decisions Made

- Cognito `UserSub` is the stable local public user ID; registration fails retryably if the provider omits it.
- Confirmation performs a command preflight before provider mutation and uses a read-only provider lookup to prove exact subject, email verification, enabled state, and `CONFIRMED` status.
- Email-based parent/child correlation remains a pending relationship input only; it is not an identity-binding authority.
- Login and refresh both use the same issuer/client/use/signature verifier and `resolve_actor()` path as protected requests.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The default uv cache path was read-restricted in the managed sandbox. Verification used `UV_CACHE_DIR=/tmp/stoa-uv-cache`; no dependency or source behavior changed.
- Non-production Cognito sandbox evidence was not configured or approved. External provider verification remains honestly **NOT RUN**; all required lifecycle evidence used deterministic local fakes and generated RSA/JWKS fixtures.

## User Setup Required

None - no external service configuration required.

## Verification

- Plan-level lifecycle/auth/security/identity suite: **93 passed**.
- Focused route inventory and auth regression: **66 passed**.
- Task 1 command/binding/replay/conflict gate: **13 passed**.
- Task 2 register/confirm/student/parent/SEC-001 gate: **28 passed**.
- Task 3 login/refresh/duplicate-email/subject/revoked/Actor gate: **17 passed**.
- Ruff on all seven changed Python files: **passed**.
- `rg -n 'get_user_by_email\(body\.email\)' src/stoa/routers/auth.py` has no login or refresh match; remaining matches belong to resend/password-recovery flows.

## Next Phase Readiness

- Plan 472-12 can build conflict quarantine/revocation on top of canonical public bindings.
- Phase 474 still owns strict Settings/global-suite fixture repair.
- Phase 475 still owns multi-write teacher takeover and relationship transactions.
- Live Cognito behavior remains an optional approved sandbox evidence step and no production/provider mutation was performed.

## Self-Check: PASSED

- All three required artifacts exist.
- All three task commits are present in history.
- Every task acceptance gate and the plan-level verification suite passed.
- Login and refresh contain no email-based local identity selection branch.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
