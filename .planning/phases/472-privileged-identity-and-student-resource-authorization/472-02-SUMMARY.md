---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 02
subsystem: security
tags: [cognito, jwt, jwks, identity-binding, authorization, dynamodb]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 01
    provides: immutable Actor, stable safe errors, and offline security doubles
provides:
  - Client-bound Cognito access-token verification with issuer-isolated bounded JWKS caching
  - Conditional unique issuer-subject to stable user identity bindings
  - Fresh active account, canonical role, and local grant intersection on every request
  - Read-only legacy dependency projection derived only from an authoritative Actor
affects: [472-03, 472-04, 472-05, 472-06, 472-07, 472-08, 472-09, 472-10, 478]

tech-stack:
  added: []
  patterns: [issuer-keyed async JWKS cache, explicit identity binding, fresh authority reads, read-only compatibility adapter]

key-files:
  created:
    - src/stoa/security/jwks.py
    - src/stoa/security/tokens.py
    - src/stoa/db/repositories/identity_repo.py
    - src/stoa/security/identity_resolution.py
  modified:
    - src/stoa/config.py
    - src/stoa/deps.py
    - src/stoa/security/identity.py
    - tests/test_auth_security.py
    - tests/test_identity_authorization.py

key-decisions:
  - "Unverified issuer input is allowlisted before any JWKS lookup, and cached signing keys are isolated first by issuer and then by kid."
  - "Known signing keys may survive a provider outage only inside the configured maximum stale window; unknown keys refresh once and otherwise fail closed."
  - "Only a conditional unique issuer-subject binding plus one matching Cognito group, active local role, and fresh active local grants can construct an Actor."
  - "Legacy route dictionaries are read-only projections of Actor authority; they cannot query or mutate Cognito, resolve email, or consume profile/token capability claims."

patterns-established:
  - "Token boundary: RS256 signature, configured issuer, time claims, token_use=access, and access client_id are mandatory before identity resolution."
  - "Identity boundary: binding, account, status, role, and grants are freshly read; any conflict or repository ambiguity denies with a stable safe code."

requirements-completed: [V9AUTH-04, V9AUTH-05]

duration: 45 min
completed: 2026-07-14
---

# Phase 472 Plan 02: Access-token verification and explicit identity boundary Summary

**Issuer/client/use-bound Cognito access tokens now resolve only through a conditional stable identity binding to one fresh active local role and authoritative grants, with bounded JWKS outage behavior and no request-time privilege repair.**

## Performance

- **Duration:** 45 min
- **Started:** 2026-07-14T19:55:06Z
- **Completed:** 2026-07-14T20:39:53Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- Added explicit issuer/client allowlists, production validation, async timeout-bound JWKS transport, issuer/kid cache isolation, single-flight refresh, rotation handling, and bounded known-key stale use.
- Enforced RS256 signature, exact configured issuer, required time claims, `token_use=access`, and `client_id`, projecting invalid/expired/provider failures through stable redacted security errors.
- Added conditional authoritative `IDENTITY#{issuer_hash}#{subject}/BINDING` rows with inventory-only reverse records and explicit re-point conflicts.
- Resolved each request through fresh binding, profile status/role, and versioned local grants; zero/multiple/mismatched/historical groups, inactive accounts, missing records, and repository ambiguity fail closed.
- Removed auth-path Cognito lookup/mutation, email fallback, profile/token capability broadening, exception swallowing, and role inference from `deps.py` while preserving a bounded read-only legacy route adapter.

## Task Commits

Each task was committed atomically:

| Task | Description | Commit |
| --- | --- | --- |
| 472-02-01 | Client-bound access-token verification and bounded JWKS cache | `6adb740` |
| 472-02-02 | Explicit active identity binding and fresh local authority | `ea27970` |
| 472-02-03 | Read-only Actor dependency chain and legacy adapter | `394183c` |

## Files Created/Modified

- `src/stoa/security/jwks.py` — asynchronous issuer-isolated bounded signing-key provider.
- `src/stoa/security/tokens.py` — verified access-token contract and redacted verification failures.
- `src/stoa/db/repositories/identity_repo.py` — conditional authoritative bindings, reverse inventory, and current authority reads.
- `src/stoa/security/identity.py` — one-role active-only Actor resolution from fresh local facts.
- `src/stoa/security/identity_resolution.py` — executable named fail-closed Wave 0 identity case inventory.
- `src/stoa/config.py` — issuer/client and JWKS timeout/cache configuration with production validation.
- `src/stoa/deps.py` — thin token, Actor, legacy projection, and safe role dependencies.
- `tests/test_auth_security.py` — offline signature, issuer/client/use, cache, rotation, outage, suspension, and mutation-sentinel coverage.
- `tests/test_identity_authorization.py` — binding conflict, role/group/status/grant, immediate revocation, and repository outage coverage.

## Decisions Made

- The verifier rejects a non-allowlisted unverified issuer before consulting any transport, preventing attacker-selected provider access.
- The JWKS provider replaces an issuer's cached keyset atomically on successful refresh and never permits a cached known key beyond the maximum stale bound.
- Non-STOA Cognito groups are ignored, but exactly one recognized plural STOA group must match the one canonical local role; `tutor` remains an explicit conflict input.
- Local account/grant reads are never cached across requests, so suspension and revocation take effect on the next dependency resolution.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Preserved the executable Wave 0 identity case module**

- **Found during:** Task 2 (explicit identity resolution)
- **Issue:** The committed Wave 0 test imports `stoa.security.identity_resolution.evaluate_identity_case`, while the plan's artifact list placed production resolution in `security/identity.py` and did not name the inventory module.
- **Fix:** Kept production resolution in `security/identity.py` and added a deliberately small inventory-only compatibility module for the named fail-closed cases.
- **Files modified:** `src/stoa/security/identity_resolution.py`
- **Verification:** The complete focused identity suite imports and executes all named cases; 46 plan tests pass.
- **Committed in:** `ea27970`

---

**Total deviations:** 1 auto-fixed (1 blocking issue).
**Impact on plan:** No authority or fallback was added; the compatibility module preserves the pre-existing executable contract while the real resolver remains authoritative.

## Issues Encountered

- One task commit initially could not create `.git/index.lock`; the lock was absent on inspection and a normal staged retry succeeded with hooks. No lock was deleted and no verification was bypassed.
- The accepted unrelated Phase 474 full-suite DynamoDB/AWS credential baseline was not changed or treated as Plan 472-02 scope.

## User Setup Required

None - no external service configuration required. Tests use injected keys, clocks, repositories, and transport without AWS credentials or network access.

## Verification

- `.venv/bin/pytest -q tests/test_auth_security.py tests/test_identity_authorization.py`: **46 passed**.
- `.venv/bin/pytest -q tests/test_auth_security.py -k 'token or issuer or client or jwks or rotation or outage'`: **16 passed, 8 deselected** at the Task 1 gate.
- `.venv/bin/pytest -q tests/test_identity_authorization.py -k 'binding or group or role or status or grant or revocation or outage'`: **17 passed, 3 deselected** at the Task 2 gate.
- Targeted Ruff across all modified Python files: **passed**.
- `rg -n 'admin_add_user_to_group|admin_get_user|get_user_by_email|custom:role' src/stoa/deps.py`: **no matches**.
- `git diff --check`: **passed**.

## Next Phase Readiness

- Ready for `472-03`: public privileged registration can now be closed against the authoritative identity vocabulary without retaining auth-path repair behavior.
- Plans 03–10 must still complete privileged onboarding, capability lifecycle, central resource policy, route migration, reconciliation, and P0 evidence. Phase 472 is not complete.

## Self-Check: PASSED

- All key created files exist on disk.
- Three atomic task commits are present.
- Every task acceptance criterion and the plan-level verification command passed.
- The phase remains in progress and no external provider or production mutation was performed.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-14*
