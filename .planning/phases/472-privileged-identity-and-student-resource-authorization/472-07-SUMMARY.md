---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 07
subsystem: security
tags: [authorization, actor, practice, adaptive-learning, parent-binding]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 05
    provides: central Actor-ResourceRef-Action-Purpose policy and fresh relationship, assignment, and capability facts
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 06
    provides: executable route dependencies and authorized-object handoff patterns
provides:
  - Actor-derived practice and adaptive self-service identity with explicit safe-public catalog classification
  - Exact teacher, administrator, and automation-preview/execute assignment scopes
  - Strict active bidirectional parent-child bindings shared by list and direct child routes
  - Load-once lesson, challenge, assignment, and child authorization before mutation or disclosure
affects: [472-08, 472-09, 472-10, 473, 475, 478]

tech-stack:
  added: []
  patterns: [explicit safe-public metadata, query-alias-aware authorization, strict binding enumeration, authorized object handoff]

key-files:
  created:
    - tests/test_practice.py
    - tests/actor_helpers.py
  modified:
    - src/stoa/security/authorization.py
    - src/stoa/security/route_authorization.py
    - src/stoa/routers/practice.py
    - src/stoa/routers/adaptive.py
    - src/stoa/routers/parents.py
    - src/stoa/services/adaptive_learning_service.py
    - tests/test_adaptive_learning.py
    - tests/test_parent_children.py

key-decisions:
  - "Only non-personalized practice catalog content is classified safe-public; progress and every personalized resource still cross Actor policy."
  - "Adaptive automation preview and execute are separate purposes and capabilities, so preview authority cannot trigger assignment writes."
  - "Parent access requires matching active forward and reverse relationship records plus active parent and student accounts; legacy parent_id, email, scan, and identifier-route fallbacks are removed."
  - "Camel-case studentId query targets are consumed by the authorization dependency itself, preventing an explicit cross-student target from falling back to Actor self."

patterns-established:
  - "Indirect write authorization: resolve the lesson, challenge, or assignment owner once, authorize that canonical student, then hand the resolved value to the handler."
  - "Strict parent enumeration: list and direct child routes apply the same ParentAuthorizationFacts.matches predicate instead of separate legacy ownership logic."
  - "Exact adaptive scope: teacher assignment and administrator capability facts name the resource type, action, purpose, and target student."

requirements-completed: [V9ACCESS-02, V9ACCESS-03]

duration: 17 min
completed: 2026-07-15
---

# Phase 472 Plan 07: Practice, adaptive, and parent route migration Summary

**Practice, adaptive-learning, and parent resources now enter through central Actor policy, with exact assignment/capability scope and one strict bidirectional parent-child authority model.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-07-14T23:07:58Z
- **Completed:** 2026-07-14T23:24:26Z
- **Tasks:** 3
- **Files modified:** 15

## Accomplishments

- Classified only non-personalized practice catalog routes as explicitly safe-public, derived personalized identity from Actor, and authorized lesson/challenge ownership before progress or mistake mutation.
- Migrated adaptive profile, recommendation, assignment, progress, and automation routes to central policy with current exact teacher assignment, administrator capability, and separate automation preview/execute authority.
- Replaced parent email/Cognito/profile-link/scan authorization and legacy identifier routes with `/me` Actor identity and active matching forward/reverse binding facts for both enumeration and direct child resources.
- Migrated affected cross-suite fixtures to canonical Actor and fact-repository overrides, including a regression that proves camel-case `studentId` cannot bypass target authorization.

## Task Commits

Each task was committed atomically:

| Task | Description | Commit |
| --- | --- | --- |
| 472-07-01 | Actor-authorized practice resources and explicit catalog classification | `d7d480b` |
| 472-07-02 | Adaptive assignments with exact teacher/admin/automation scope | `768c3f0` |
| 472-07-03 | Strict active bidirectional parent-child bindings | `4fad872` |
| Regression | Remove legacy adaptive authorization fallbacks | `4203c0c` |
| Regression | Migrate affected fixtures and query targets to Actor authorization | `cc5f588` |

## Files Created/Modified

- `src/stoa/security/route_authorization.py` — safe-public metadata, typed student-resource dependencies, and query-alias-aware target authorization.
- `src/stoa/security/authorization.py` — exact adaptive assignment, automation, and administrator capability purpose mappings.
- `src/stoa/routers/practice.py` — Actor self-service, authorized indirect resources, and canonical progress targets.
- `src/stoa/routers/adaptive.py` — load-once assignment handoff and separate preview/execute policy boundaries.
- `src/stoa/routers/parents.py` — `/me` Actor routes and strict shared binding checks without legacy lookup/scan routes.
- `src/stoa/services/adaptive_learning_service.py` — removed service-local profile-link and role authorization fallbacks.
- `tests/test_practice.py`, `tests/test_adaptive_learning.py`, `tests/test_parent_children.py` — denial, positive-control, outage-before-effect, and exact-scope coverage.
- `tests/actor_helpers.py` and affected route suites — canonical Actor/fresh-fact test isolation.

## Decisions Made

- Practice lesson and challenge catalog reads may be broadly authenticated only when explicitly marked safe-public; progress, personalized roadmaps, attempts, mistakes, and recommendations remain student-resource operations.
- A teacher needs a current assignment matching target, resource type, action, and purpose. An administrator needs the exact current capability grant; role alone grants neither path.
- Assignment automation preview and execution are intentionally non-substitutable authorities, and execution authorizes before producing any write.
- Parent list and direct child routes share identical active account and active forward/reverse binding requirements. Removed legacy routes are not retained as compatibility aliases.
- Central policy's hidden `404 resource_not_found` remains the cross-student denial contract; the `studentId` alias is resolved inside the dependency so caller intent cannot be discarded.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- One normal regression commit initially could not create `.git/index.lock` under the managed filesystem. An approved normal retry committed the verified files; no lock was removed and no hook was bypassed.
- Full-suite observation is **766 passed, 33 failed**, improving the Plan 472-06 **766 passed, 44 failed** baseline without introducing a new failure. Remaining failures are known AI terminology expectations, strict production Cognito configuration fixtures, unimplemented reconciliation and Plan 472-08 RED modules, and the same stale production-settings fixture family. They were not treated as Plan 472-07 verification success or changed outside this plan.
- No AWS credentials, network, provider call, production mutation, or Phase 475 transaction rewrite was used.

## User Setup Required

None - no external service configuration required.

## Verification

- `.venv/bin/pytest -q tests/test_practice.py tests/test_adaptive_learning.py tests/test_parent_children.py tests/test_student_authorization_matrix.py`: **123 passed**.
- Plan suite plus cross-suite target regressions: **125 passed**.
- Task 1 focused gate: **6 passed**; Task 2 focused gate: **22 passed**; Task 3 parent suite: **58 passed**.
- Registered route classification: practice **14**, adaptive **15**, parent **13** decorators classified.
- Targeted Ruff across implementation and affected tests: **passed**.
- `git diff --check`: **passed**.
- Full suite (observation only): **766 passed, 33 failed**, with the known limitations recorded above.

## Next Phase Readiness

- Ready for `472-08` to migrate teacher, assistance, conversation-adjacent, and AI-tool route families using the same exact-scope and authorized-object patterns.
- Plans 08-10 remain pending. Phase 472 stays `executing` and is not complete.

## Self-Check: PASSED

- Every required artifact exists, each plan task has an atomic implementation commit, and the complete plan verification is green.
- Practice, adaptive, and parent registered routes are classified and no relevant router retains bare `get_current_user`, broad `require_role`, parent email/Cognito/scan authorization, or adaptive service-local role fallback.
- The exact milestone name, roadmap structure, and Phase 472 executing status remain unchanged; no phase completion was recorded.
- No AWS/network/production mutation or Phase 475 write-transaction scope was introduced.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
