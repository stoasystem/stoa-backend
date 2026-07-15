---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 15
subsystem: auth
tags: [cognito, error-boundary, redaction, client-contract, correlation]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    provides: canonical public identity binding, recursive public route declarations, and request correlation
provides:
  - One closed operation-aware taxonomy for all eight public identity-provider operations
  - Exact top-level safe error bodies with server-owned correlation and bounded retry headers
  - Exhaustive deterministic client recovery actions with endpoint-wide secret canaries
affects: [phase-474-testing, phase-478-clients, public-auth, account-recovery]

tech-stack:
  added: []
  patterns: [closed provider normalization, redacted telemetry projection, actionable client recovery]

key-files:
  created:
    - src/stoa/security/public_auth_errors.py
    - tests/test_public_auth_error_boundary.py
  modified:
    - src/stoa/security/errors.py
    - src/stoa/security/client_error_actions.py
    - src/stoa/routers/auth.py
    - docs/security/client-error-actions.json
    - tests/test_client_error_actions.py
    - tests/test_auth_account_lifecycle.py

key-decisions:
  - "Public provider failures expose exactly code, actionable message, and server-owned correlationId; provider diagnostics never enter the body."
  - "Unknown provider failures become a stable 503 with bounded Retry-After, while writes are never automatically replayed."
  - "Support is requested only for account recovery, disabled accounts, or persistent outages, and always with the correlation reference."

patterns-established:
  - "Provider error codes are interpreted only inside one operation-aware closed mapping."
  - "Internal telemetry contains operation, correlation, normalized category, and keyed provider-code digest only."

requirements-completed: [V9AUTH-05]

duration: 8 min
completed: 2026-07-15
---

# Phase 472 Plan 15: Safe Structured Public Cognito Error Boundary Summary

**All eight public authentication operations now share one redacted provider boundary, exact structured responses, and simple client actions that clearly tell users whether to retry, sign in again, verify email, correct input, request a new code, or contact support.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-15T13:48:34Z
- **Completed:** 2026-07-15T13:56:24Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- Added a closed operation-aware taxonomy covering register, login, verification resend/confirm, forgot/reset password, refresh, and logout.
- Replaced provider-specific and interpolated public exceptions with exact `{code,message,correlationId}` responses and a matching `X-Correlation-ID` header.
- Kept account-existence hiding and Plan 11 subject-bound login/registration behavior intact.
- Added eight-endpoint unknown-code canaries proving raw provider code, message, email, token, pool, operation name, and exception representation cannot escape.
- Regenerated an exhaustive byte-stable client action contract with explicit next steps and bounded retry behavior.

## Task Commits

Each task was committed atomically:

1. **Task 1: Define the structured public provider error taxonomy** - `ae37969` (feat)
2. **Task 2: Route every public Cognito endpoint through the boundary** - `60ad7d4` (feat)
3. **Task 3: Regenerate client actions and endpoint canary matrix** - `69413e9` (test)

## Files Created/Modified

- `src/stoa/security/public_auth_errors.py` - Closed provider operation enum, normalization map, safe response projection, and redacted telemetry.
- `src/stoa/security/errors.py` - Stable public auth codes, statuses, and clearly actionable messages.
- `src/stoa/security/client_error_actions.py` - Exhaustive recovery actions and bounded retry interpreter contract.
- `src/stoa/routers/auth.py` - One provider failure boundary across all eight public authentication operations.
- `tests/test_public_auth_error_boundary.py` - Known mapping, exact shape, retry, telemetry, and endpoint canary matrix.
- `tests/test_client_error_actions.py` - Exhaustiveness, deterministic generation, and bounded client behavior.
- `tests/test_auth_account_lifecycle.py` - Updated lifecycle assertions for the exact top-level structured body.
- `docs/security/client-error-actions.json` - Regenerated version 472.2 client contract.

## Decisions Made

- Vague messages were removed. Persistent outages explicitly say to retry first and contact support with the displayed reference only if the problem continues.
- Account conflicts and disabled accounts explicitly direct the user to support with the correlation reference because self-service retry cannot safely resolve those states.
- Rate limiting returns 429 without automatic replay. Unknown dependency failures return 503 with a 15-second bounded Retry-After, but client automation remains limited to idempotent reads.
- Provider codes are represented internally only by a process-keyed digest plus a closed category, preventing raw codes or messages from becoming public or durable telemetry.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Existing lifecycle tests asserted FastAPI's historical nested `detail` shape. They were updated to assert the new required exact top-level security body; no production behavior was weakened.
- The managed environment's default uv cache is read-restricted, so verification used `UV_CACHE_DIR=/tmp/stoa-uv-cache`; source and dependency behavior were unchanged.

## User Setup Required

None - no external service configuration required.

## Verification

- Complete plan suite: **105 passed**.
- Boundary/client taxonomy suite: **36 passed**.
- Eight public operations each passed an unknown provider code and secret-bearing message canary without leakage to the public response or telemetry projection.
- Ruff across all changed Python files: **passed**.
- Client contract generated twice and `--check` passed with a clean diff.
- Unsafe provider interpolation search returned no matches in `src/stoa/routers/auth.py`.
- No AWS/network/provider/production mutation was performed; external sandbox evidence remains honestly **NOT RUN**.

## Next Phase Readiness

- Plan 472-16 can run the final integrated authorization/authentication evidence gate.
- Phase 474 remains owner of strict global Settings fixture repair.
- Phase 475 remains owner of atomic teacher takeover and multi-write lifecycle transactions.

## Self-Check: PASSED

- Both required plan artifacts exist.
- All three task commits are present in history.
- Every task acceptance criterion and plan-level verification command passed.
- STATE milestone naming remains intact and Plan 472-16 is the only remaining plan.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
