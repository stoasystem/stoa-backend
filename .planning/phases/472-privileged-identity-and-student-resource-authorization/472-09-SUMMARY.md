---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 09
subsystem: security
tags: [authorization, admin, notifications, reports, capabilities, actor]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 04
    provides: authoritative local capability grants and routine privileged identity lifecycle
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 05
    provides: central Actor-ResourceRef-Action-Purpose policy and safe denial semantics
provides:
  - Exact executable capability classification for all 109 admin method-path registrations
  - Actor-owned notification collection, preference, digest, event, and push-token authorization
  - Distinct notification inspection and delivery-health administrator capabilities
  - Scoped report metadata, recovery, export, external-send, retention, and governance controls
affects: [472-10, 473, 475, 478, admin-operations, notifications, reports]

tech-stack:
  added: []
  patterns: [registered method-path capability table, Actor-owned indirect resource resolution, capability-before-resolver denial]

key-files:
  created:
    - src/stoa/security/admin_authorization.py
    - tests/test_admin_authorization.py
  modified:
    - src/stoa/routers/admin.py
    - src/stoa/routers/notifications.py
    - src/stoa/security/authorization.py
    - src/stoa/security/route_authorization.py
    - src/stoa/services/notification_service.py
    - tests/test_admin_report_ops.py
    - tests/test_notifications.py

key-decisions:
  - "Admin authority is selected from the registered HTTP method and route path, then checked against a fresh exact local grant; the /admin prefix and admin role grant nothing by themselves."
  - "Notification events and push tokens resolve their canonical owner before mutation; role broadcasts are not mutable user-owned events."
  - "Ineligible roles and missing capabilities deny before resource lookup, while eligible scoped grants resolve indirect job and delivery identifiers and convert repository outages to safe 503."
  - "Curriculum author, reviewer, publisher, migration, and analytics capabilities remain separate and are carried from Actor into existing capability-aware services."

patterns-established:
  - "Admin completeness: enumerate every APIRoute registered below /admin in main.py and require exactly one executable classifier dependency."
  - "Owner handoff: notification handlers consume the already-authorized event or token object rather than reloading caller identifiers."
  - "Operator denial order: reject role-only, break-glass-only, and missing-capability callers before repository access; resolve target scope only for an eligible grant."

requirements-completed: [V9AUTH-02, V9ACCESS-02, V9ACCESS-03]

duration: 8 min
completed: 2026-07-15
---

# Phase 472 Plan 09: Admin and operator route capability migration Summary

**All 109 admin-prefixed method-path registrations now require fresh exact capabilities, while notification events, digests, preferences, and push tokens are Actor-owned and resolved before effects.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-14T23:57:10Z
- **Completed:** 2026-07-15T00:05:14Z
- **Tasks:** 4
- **Files modified:** 20

## Accomplishments

- Classified every `/admin` route registered in `main.py`, including both notification administrator routes, by exact capability, purpose, action, resource family, and target coordinates with positive and denial controls.
- Removed broad role authority from the admin surface while preserving exact curriculum operator workflows and ensuring identity, refund, binding repair, export, external send, legal hold, and privilege actions reject role-only and break-glass callers.
- Migrated notification list, preferences, digest, event, and push-token routes to Actor ownership; cross-user event IDs, token references, and provider token aliases return hidden 404 before any mutation.
- Resolved recovery job and handoff delivery identifiers inside authorization, with missing 404, known denial 403, dependency outage 503, and no service mutation before authorization.

## Task Commits

| Task | Description | Commit |
| --- | --- | --- |
| 472-09-01 | Exact capability classification for every registered admin route | `92ab421` |
| 472-09-04 | Actor-owned notification resources and distinct admin notification reads | `df49bf2` |
| 472-09-02 | Scoped report operation capability controls | `9796798` |
| 472-09-03 | Indirect recovery job and handoff delivery resolution | `d490b77` |
| Regression | Reject ineligible operators before resource resolution | `d065de6` |
| Regression | Preserve exact curriculum operator workflows and fixtures | `77cac02` |

## Files Created/Modified

- `src/stoa/security/admin_authorization.py` — exhaustive runtime method/path classifier and exact Actor grant dependency for all admin registrations.
- `src/stoa/security/authorization.py` — notification resource/purpose types and central operator capability evaluation.
- `src/stoa/security/route_authorization.py` — Actor-self, event-owner, and push-token-owner load-once dependencies.
- `src/stoa/routers/admin.py` — all 107 physical admin decorators use the executable classifier rather than role authority.
- `src/stoa/routers/notifications.py` and `src/stoa/services/notification_service.py` — Actor-owned routes and authorized-object mutation handoff.
- `tests/test_admin_authorization.py` — 109-route completeness, exact capability, scope, break-glass, outage, and distinct notification controls.
- Affected admin, curriculum, notification, report, account, BI, moderation, and usage suites — canonical Actor grant fixtures.

## Decisions Made

- Kept existing report and operational service behavior, but placed exact authorization before every handler effect; handlers receive the Actor-derived legacy projection only where the service API still requires it.
- Permitted teachers to use admin-prefixed curriculum operations only with the exact existing author/reviewer/publisher/migration/analytics grant. Teacher or administrator role alone remains insufficient.
- Treated notification role broadcasts as operational events, not personal mutable resources; only a directly addressed recipient may mark or archive an event.
- Used capability-first denial to prevent role-only callers from probing resource stores, then performed scoped indirect resolution for eligible grants so repository outages remain distinguishable as safe 503.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Preserved multi-capability curriculum lifecycle contracts**

- **Found during:** Full-suite verification after Task 3
- **Issue:** A first-pass one-capability classifier blocked existing exact author preview, reviewer approval, publisher, migration, and analytics positive controls even though role-only denial was correct.
- **Fix:** Added explicit alternate exact capabilities per curriculum route and carried Actor grants into the existing capability-aware service projection; migrated affected fixtures to global operator grants.
- **Files modified:** `src/stoa/security/admin_authorization.py`, `src/stoa/security/authorization.py`, `tests/actor_helpers.py`, curriculum/admin fixture suites.
- **Verification:** Curriculum operations, migration, and analytics: **33 passed**; full suite returned to the known 33-failure baseline.
- **Committed in:** `77cac02`

**2. [Rule 2 - Missing Critical] Denied ineligible callers before indirect repository resolution**

- **Found during:** Plan-level report verification
- **Issue:** Recovery job and delivery resolvers ran before rejecting a non-admin or missing-capability caller, turning ordinary denial fixtures into dependency failures and permitting a store probe.
- **Fix:** Added role and capability eligibility rejection before target resolution, while retaining exact scope resolution and 503 behavior for eligible operators.
- **Files modified:** `src/stoa/security/admin_authorization.py`
- **Verification:** Report recovery/handoff focused gate: **191 passed, 68 deselected**.
- **Committed in:** `d065de6`

**Total deviations:** 2 auto-fixed (2 missing critical authorization integrations). **Impact:** Both tightened the intended policy boundary and restored exact positive controls without role fallback or scope expansion.

## Issues Encountered

- The first full-suite observation exposed 19 new curriculum fixture/capability failures. They were fixed and the repeat full suite reported **903 passed, 33 failed**, exactly the known 33-failure baseline with no new failures.
- The remaining 33 failures are unchanged baseline families: historical AI terminology expectations, strict production Cognito configuration fixtures, pending reconciliation and route inventory work, report production settings, and subscription production fixtures.
- No AWS credentials, network access, provider calls, production mutation, or Phase 475 transaction redesign was used.

## User Setup Required

None - no external service configuration required.

## Verification

- Task 01 command: **43 passed, 109 deselected**; complete registered admin policy matrix: **115 passed** before later additions.
- Task 04 command: **139 passed, 11 deselected**.
- Task 02 command: **191 passed, 68 deselected**.
- Task 03 command: **165 passed**.
- Final plan suite: **328 passed**.
- Full Python suite: **903 passed, 33 failed**; delta from known baseline: **+125 passed, 0 new failures**.
- Targeted Ruff and `git diff --check`: **passed**.

## Next Phase Readiness

- Ready for `472-10` to independently inspect the full FastAPI dependency tree and generate the final deterministic route inventory/reconciliation evidence.
- Phase 472 remains `executing`; Plan 10 is still pending and no phase-complete status has been recorded.

## Self-Check: PASSED

- Every admin-prefixed registered method/path has one executable classification and positive/negative exact-capability proof.
- Notification owner, other-user, missing-resource, wrong-capability, role-only, break-glass, and authorization-outage controls pass before mutation.
- All six production/regression commits exist, the final plan suite is green, and the full-suite failure count did not increase.
- Exact milestone name, roadmap structure, and executing status are unchanged; no external system was contacted.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
