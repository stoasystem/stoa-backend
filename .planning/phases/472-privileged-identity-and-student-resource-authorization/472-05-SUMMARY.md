---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 05
subsystem: security
tags: [authorization, parent-binding, teacher-scope, capabilities, break-glass, audit]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 02
    provides: immutable active Actor resolution and fresh authoritative grants
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 04
    provides: versioned local capabilities and redacted security audit evidence
provides:
  - One deterministic Actor-ResourceRef-Action-Purpose authorization policy
  - Fresh strict bidirectional parent relationship and active-account facts
  - Current question/session and exact scoped teacher assignment authorization
  - Purpose-specific admin support, content-review, safety, and break-glass decisions
  - Load-once authorized resources, safe existence taxonomy, and outage-before-handler behavior
affects: [472-06, 472-07, 472-08, 472-09, 472-10, 473, 475, 478]

tech-stack:
  added: []
  patterns: [load-and-return authorized resource, fresh no-cache facts, exact capability scope, allowlisted decision evidence]

key-files:
  created: []
  modified:
    - src/stoa/security/authorization.py
    - src/stoa/db/repositories/user_repo.py
    - src/stoa/db/repositories/question_repo.py
    - src/stoa/db/repositories/security_audit_repo.py
    - tests/test_identity_authorization.py
    - tests/test_student_authorization_matrix.py

key-decisions:
  - "One deterministic policy evaluates immutable Actor, canonical ResourceRef, Action, and Purpose after a single resource load and fresh fact reads."
  - "Parent authorization requires matching active forward and reverse rows with equal relationship/version plus active parent and student accounts; legacy profile links never authorize."
  - "Teacher task authority is limited to the current question/conversation/session, while broader resources require a separate active exact resource-action-purpose assignment."
  - "Admin role grants nothing by itself; support metadata, content review, safety review, and incident break-glass require separate exact scoped capabilities."
  - "Break-glass is at most fifteen minutes, read-only, incident-bound, and requires notification plus independent-review evidence."

patterns-established:
  - "Resolver identity: authorize_and_resolve loads once, fails 404/503 before handlers, and returns the same authorized mapping to the handler."
  - "Immediate revocation: account, relationship, dispatch/session, assignment, and capability authority is read per request with no cross-request allow cache."
  - "Safe evidence: decisions and break-glass obligations are appended from allowlisted scalar fields without content, tokens, object keys, or provider payloads."

requirements-completed: [V9ACCESS-01, V9ACCESS-03]

duration: 15 min
completed: 2026-07-15
---

# Phase 472 Plan 05: Central actor-resource-action-purpose authorization policy Summary

**One fail-closed policy now decides student-resource access from current ownership, relationship, teacher-task/assignment, exact capability, and incident evidence while returning the same resolved object to authorized handlers.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-14T22:25:00Z
- **Completed:** 2026-07-14T22:40:11Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Implemented the central typed authorization policy, canonical resource reference, authorized-resource wrapper, deterministic 404/403 decision taxonomy, redacted decision event, and outage-safe load-once dependency boundary.
- Required fresh matching active forward/reverse formal parent rows, equal relationship/version, and active accounts; legacy `parent_id`, pending/revoked/asymmetric/stale rows never authorize.
- Restricted teachers to current dispatch/question/session work or a separate exact active assignment; queue visibility, prior dispatch, stale session, suspension, and broader student resources deny.
- Required exact purpose/scoped admin capabilities, emitted bounded support metadata only, and enforced a fifteen-minute read-only incident break-glass contract with notification and independent-review evidence.

## Task Commits

Each task was committed atomically:

| Task | Description | Commit |
| --- | --- | --- |
| 472-05-01 | Central owner and strict bidirectional parent policy | `b59d417` |
| 472-05-02 | Current teacher task and exact assignment scope | `6f603cf` |
| 472-05-03 | Purpose-bounded admin support and break-glass | `7dafdc2` |

## Files Created/Modified

- `src/stoa/security/authorization.py` — deterministic policy, typed resource/fact contracts, fresh fact loader, load-once authorization dependency, support projection, and executable matrix helpers.
- `src/stoa/db/repositories/user_repo.py` — consistent active account reads and exact forward/reverse formal parent-binding reads with versioned rows.
- `src/stoa/db/repositories/question_repo.py` — consistent question, teacher-session, and scoped assignment reads; no takeover/session write redesign.
- `src/stoa/db/repositories/security_audit_repo.py` — allowlisted policy events plus notification and independent-review break-glass evidence.
- `tests/test_identity_authorization.py` — redacted break-glass evidence proof.
- `tests/test_student_authorization_matrix.py` — positive controls and owner, parent, teacher, admin, support, outage, hidden-resource, and break-glass negative matrices.

## Decisions Made

- A resource resolver executes once; repository inability becomes `authorization_temporarily_unavailable` before any handler mutation, and an allow returns that exact loaded mapping.
- `relationship_known` controls the existence-hiding boundary: unrelated actors receive indistinguishable safe 404 responses, while actors allowed to know the relationship receive a 403 for a forbidden action.
- Parent authorization reads both exact formal rows and both accounts consistently. Existing legacy scans remain reconciliation inputs only and are never consumed by the policy.
- Current teacher task facts permit only linked question/conversation operations. Separate assignment scope must exactly match resource/action/purpose; generic learning, queue, role, or stale ownership facts do not broaden access.
- Support lookup and student content review use separate capabilities. Break-glass cannot mutate, resolve, export, externally send, manage privilege, or mutate curriculum.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The Task 3 commit initially could not create `.git/index.lock` under the managed filesystem. A normal approved retry staged and committed the same verified files; no lock was removed and no hook was bypassed.
- No AWS credentials, network access, provider call, production mutation, Phase 475 relationship transaction, or takeover/session convergence write was attempted. The accepted unrelated DynamoDB credential baseline was not changed.

## User Setup Required

None - no external service configuration required.

## Verification

- `.venv/bin/pytest -q tests/test_identity_authorization.py tests/test_student_authorization_matrix.py tests/test_parent_children.py tests/test_teacher_dispatch.py`: **150 passed**.
- `.venv/bin/pytest -q tests/test_teacher_reply_sla.py`: **8 passed**.
- Task 1 owner/parent/hidden/outage gate: **20 passed, 29 deselected**.
- Task 2 teacher/dispatch/assignment/scope gate: **29 passed, 20 deselected**.
- Task 3 admin/support/break-glass/redaction gate: **14 passed, 52 deselected**.
- Targeted Ruff across all plan implementation and test surfaces: **passed**.
- `git diff --check`: **passed**.

## Next Phase Readiness

- Ready for `472-06` to attach executable policy dependencies to every identifier-bearing route and generate the route inventory from those declarations.
- Phase 475 still owns transactional parent-binding writes/symmetry repair and atomic teacher takeover/session convergence. Plans 06–10 remain; Phase 472 stays executing and is not complete.

## Self-Check: PASSED

- All required artifacts exist and all three atomic task commits are present.
- Every task acceptance criterion and the plan-level verification command passed with positive allow controls.
- The exact milestone name is unchanged, roadmap structure is preserved, and Phase 472 is not marked complete.
- No AWS/network/production mutation or Phase 475 transactional scope was introduced.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
