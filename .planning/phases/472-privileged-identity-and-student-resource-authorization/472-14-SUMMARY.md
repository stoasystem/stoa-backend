---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 14
subsystem: authorization
tags: [audit, hmac, correlation, dynamodb, fail-closed]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    provides: central Actor policy, complete route inventory, and immutable current capability grants
provides:
  - Server-owned request correlation shared by policy evidence, safe errors, and response headers
  - Durable keyed and redacted authorization decision evidence across generated, direct, operator, and admin paths
  - Bounded replay-safe probe aggregation and fail-closed mandatory-evidence semantics
affects: [phase-474-testing, phase-480-observability, authorization, admin-operations]

tech-stack:
  added: []
  patterns: [evidence-before-effect, keyed resource identity, bounded optimistic aggregate, denial-preserving degradation]

key-files:
  created:
    - src/stoa/security/request_correlation.py
    - tests/test_authorization_audit.py
    - tests/audit_helpers.py
  modified:
    - src/stoa/config.py
    - src/stoa/deps.py
    - src/stoa/security/authorization.py
    - src/stoa/security/errors.py
    - src/stoa/security/route_authorization.py
    - src/stoa/security/admin_authorization.py
    - src/stoa/db/repositories/security_audit_repo.py
    - src/stoa/routers/parents.py
    - src/stoa/routers/practice.py
    - src/stoa/routers/adaptive.py
    - src/stoa/routers/conversations.py
    - tests/test_admin_authorization.py
    - tests/test_student_authorization_matrix.py
    - tests/test_questions.py
    - tests/test_conversations.py
    - tests/test_parent_children.py
    - tests/actor_helpers.py

key-decisions:
  - "Canonical authorization correlation IDs are generated server-side and never reuse an inbound header."
  - "Audit rows and partition keys use keyed actor/resource fingerprints; raw student, owner, target, email, and key material are never persisted."
  - "Only owner self-service allows may proceed without durable evidence; every parent, teacher, admin, capability, break-glass, export, and external-send allow is evidence-before-effect."
  - "Probe aggregates use fixed safe-class windows with conditional version writes, capped counts, capped event-ID ledgers, and deterministic thresholds."

requirements-completed: [V9ACCESS-01, V9ACCESS-03]

duration: 45 min
completed: 2026-07-15
---

# Phase 472 Plan 14: Durable authorization decisions and bounded probe evidence Summary

**Every central authorization decision now shares a server-owned correlation ID, persists keyed redacted evidence before sensitive effects, and fails closed without leaking resource existence when the evidence store is unavailable.**

## Performance

- **Duration:** 45 min
- **Completed:** 2026-07-15
- **Tasks:** 3
- **Files modified:** 20

## Accomplishments

- Added canonical UUIDv4 request correlation cached on request state and returned through the response or safe error header/body.
- Added validated, versioned authorization-audit key configuration with retained-key replay recognition and no persisted key material.
- Added one recording gateway for `authorize_and_resolve`, direct policy evaluation, operator capability, and all registered admin decision families.
- Persisted only allowlisted decision dimensions plus keyed actor/resource fingerprints, with exact replay idempotency and same-request cross-resource separation.
- Added one fixed-window probe aggregate per safe actor/resource/action/purpose/result class with conditional optimistic writes, bounded count, bounded event ledger, TTL, and threshold evidence.
- Preserved safe 403/404 behavior on denial evidence outage and converted mandatory allows to correlated safe 503 before handlers, streams, exports, providers, or other effects.

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire canonical request correlation and durable decision evidence** - `f77e66c` (feat)
2. **Task 2: Bound and persist repeated authorization probes** - `747498f` (feat)
3. **Task 3: Fail closed under authorization audit outage** - `a5b92df` (fix)

## Decisions Made

- The client cannot select or replay the canonical authorization correlation ID; inbound `X-Correlation-ID` is ignored.
- Resource identity uses length-delimited HMAC-SHA256 material and event identity includes the resource fingerprint, so two resources in one request cannot collapse.
- Rotation writes only with the active key but checks retained previous-key event identities for immutable replay recognition.
- Missing local audit-key configuration yields an unavailable sink; production rejects a missing or placeholder key during Settings validation.
- Denial persistence and aggregation failure never changes the original denial, while mandatory-allow failure prevents the authorized object from reaching the handler.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Made security decision exceptions traceback-safe**
- **Found during:** Task 1
- **Issue:** Python exception propagation attempted to attach a traceback to the frozen `SecurityDecisionError` dataclass and raised `FrozenInstanceError`, hiding the intended safe outage.
- **Fix:** Kept the slotted exception but removed dataclass freezing so standard exception traceback machinery works.
- **Files modified:** `src/stoa/security/errors.py`
- **Verification:** Real admin outage returns the intended correlated safe 503 and no internal exception escapes.
- **Commit:** `f77e66c`

**2. [Rule 2 - Missing Critical] Wired the teacher-help conversation helper caller**
- **Found during:** Task 3 full plan regression
- **Issue:** The existing direct `authorize_conversation_resource()` caller was outside the planner's initial file list and lacked the newly mandatory correlation/sink arguments.
- **Fix:** Injected the canonical correlation and audit sink into the real teacher-help dependency and forwarded both to the shared gateway.
- **Files modified:** `src/stoa/routers/conversations.py`, `tests/test_conversations.py`
- **Verification:** Complete plan regression reports 298 passed, including teacher-help and current-teacher controls.
- **Commit:** `a5b92df`

**3. [Rule 3 - Blocking] Kept focused route regressions offline**
- **Found during:** Tasks 1 and 3
- **Issue:** Newly mandatory evidence caused existing route tests to reach the real DynamoDB sink despite their other repository fakes.
- **Fix:** Added and injected a deterministic memory audit double in affected test harnesses; production dependency behavior is unchanged.
- **Files modified:** `tests/audit_helpers.py`, `tests/actor_helpers.py`, and focused route test fixtures.
- **Verification:** Complete plan regression runs without AWS credentials or network access.
- **Commit:** `f77e66c`, `a5b92df`

**Total deviations:** 3 auto-fixed (1 bug, 1 missing critical call path, 1 test blocker). **Impact:** The fixes were necessary to preserve safe exception transport, complete the promised production call graph, and keep verification isolated; no scope or product behavior broadened.

## Issues Encountered

- The default uv cache remains read-restricted in the managed sandbox. Verification used `UV_CACHE_DIR=/tmp/stoa-uv-cache`; source behavior was unchanged.
- No AWS, network, external provider, sandbox, or production mutation was performed.

## User Setup Required

- Production must configure a non-placeholder `AUTHORIZATION_AUDIT_ACTIVE_KEY_ID` and `AUTHORIZATION_AUDIT_ACTIVE_KEY`.
- Retained previous key IDs/secrets must remain configured for at least the decision retry/probe TTL during rotation.

## Verification

- Task 1 correlation/persistence/redaction/call-site gate: **6 passed**.
- Task 2 probe/aggregate/bounded/hidden/retry gate: **8 passed**.
- Task 3 outage/handler/mandatory/correlation/break-glass gate: **20 passed**.
- Complete plan authorization/identity/student/questions/conversations/parent/teacher/admin regression: **298 passed**.
- Ruff across every changed Python source/test file: **passed**.
- AST call-site completeness and production `rg` inventory: **passed**.
- `git diff --check`: **passed**.

## Next Phase Readiness

- Plan 472-13 can consume the correlation/sink dependency graph while tightening recursive sensitive-identifier inventory.
- Plan 472-15 can use the canonical correlation boundary for safe public Cognito error projection.
- Phase 480 retains broader alert delivery; this plan supplies bounded durable evidence only.
- Phase 474/475 ownership boundaries remain unchanged.

## Self-Check: PASSED

- All three required artifacts exist.
- All three task commits are present in history.
- Every task acceptance gate and the complete plan verification command passed.
- Audit rows contain no raw resource, student, owner, target, email, content, provider detail, or key material canaries.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
