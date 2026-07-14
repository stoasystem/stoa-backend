---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 04
subsystem: security
tags: [capabilities, teacher-onboarding, cognito, privileged-identity, audit, dynamodb]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 02
    provides: explicit identity binding, active-only Actor resolution, and fresh local grants
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 03
    provides: public privilege barrier and canonical teacher-only contracts
provides:
  - Conditional versioned local capability grants with immediate request-time revocation
  - Immutable teacher applications, exact-version review, and digest-only invitations
  - Same-verified-email single-use deny-first teacher activation with resumable commands
  - Capability-bounded routine administrator and grant lifecycle commands
  - Bootstrap/disaster-only administrator script with explicit binding and redacted evidence
affects: [472-05, 472-06, 472-07, 472-08, 472-09, 472-10, 478]

tech-stack:
  added: []
  patterns: [version-checked local grants, immutable application versions, digest-only invitation, deny-first resumable command, local-first revocation, allowlisted audit]

key-files:
  created:
    - src/stoa/db/repositories/capability_repo.py
    - src/stoa/db/repositories/security_audit_repo.py
    - src/stoa/db/repositories/teacher_application_repo.py
    - src/stoa/db/repositories/privileged_identity_repo.py
    - src/stoa/services/teacher_application_service.py
    - src/stoa/services/privileged_identity_service.py
    - src/stoa/routers/teacher_applications.py
  modified:
    - src/stoa/config.py
    - src/stoa/deps.py
    - src/stoa/main.py
    - src/stoa/routers/admin.py
    - src/stoa/security/tokens.py
    - src/stoa/services/curriculum_ops_service.py
    - scripts/provision_production_admin.py
    - tests/test_curriculum_ops.py
    - tests/test_identity_authorization.py
    - tests/test_provision_production_admin.py
    - tests/test_teacher_onboarding.py

key-decisions:
  - "Only current versioned local grants projected from Actor authority can authorize capabilities; role, token, profile, metadata, permission, and scope inputs do not broaden them."
  - "Teacher approval creates only a digest-bound expiring invitation; local teacher state remains pending until provider group, profile, and explicit issuer-subject binding reconcile."
  - "Routine privilege changes require an active admin_identity_manager and one immutable idempotent command; local suspension/revocation precedes provider defense steps."
  - "Bootstrap administration is limited to first-admin or disaster-recovery purposes and never supplies implicit request-path capabilities."

patterns-established:
  - "Deny-first activation: create pending local state, perform idempotent provider/binding steps, then and only then mark active."
  - "Safe lifecycle evidence: build append-only audit rows from an allowlist instead of filtering serialized provider or application payloads."

requirements-completed: [V9AUTH-02, V9AUTH-03, V9AUTH-04]

duration: 26 min
completed: 2026-07-14
---

# Phase 472 Plan 04: Versioned capabilities and privileged identity lifecycle Summary

**Current local grants now control every privilege change, while teacher and routine administrator identities activate only through capability-approved, idempotent, deny-first lifecycle commands with redacted evidence.**

## Performance

- **Duration:** 26 min
- **Started:** 2026-07-14T21:58:00Z
- **Completed:** 2026-07-14T22:24:04Z
- **Tasks:** 3
- **Files modified:** 19

## Accomplishments

- Added independent capability grants with grant identity, scope, grantor, reason, effective/expiry bounds, status, version checks, conditional grant/revoke/restore, and consistent current reads on every identity resolution.
- Replaced curriculum claim/profile/permission/scope unions with the authoritative Actor capability projection, so teacher or admin role alone never confers author, reviewer, or publisher authority.
- Added immutable bounded teacher application versions without document upload/storage, exact-version reviewer decisions, digest-only expiring invitations, same-verified-email consumption, and replay/concurrency-safe activation commands.
- Kept teacher profiles non-active across provider failures and resumed the same command until exactly one canonical group, local profile, issuer-subject binding, and evidence chain reconciled.
- Added authenticated routine admin provision/suspend/revoke/restore and capability endpoints guarded by `admin_identity_manager`, with local-first immediate revocation and idempotent conflict checks.
- Narrowed the production-admin script to explicit first-admin/disaster-recovery use, with dry-run zero writes, active profile plus binding evidence, conflict checks, and output that omits email, password/token material, and provider payloads.

## Task Commits

Each task was committed atomically:

| Task | Description | Commit |
| --- | --- | --- |
| 472-04-01 | Authoritative versioned local capabilities and safe audit | `baa287a` |
| 472-04-02 | Immutable teacher application and deny-first invitation activation | `7c2ecc9` |
| 472-04-03 | Capability-bounded routine admin lifecycle and bootstrap isolation | `1656be6` |

## Files Created/Modified

- `src/stoa/db/repositories/capability_repo.py` — conditional versioned grant lifecycle and consistent effective/expiry filtering.
- `src/stoa/db/repositories/security_audit_repo.py` — append-only allowlisted lifecycle evidence.
- `src/stoa/db/repositories/teacher_application_repo.py` — immutable applications/reviews, digest invitations, and versioned activation commands.
- `src/stoa/db/repositories/privileged_identity_repo.py` — immutable idempotent routine privilege commands.
- `src/stoa/services/teacher_application_service.py` — public candidacy, exact review, invitation, and deny-first activation orchestration.
- `src/stoa/services/privileged_identity_service.py` — manager-guarded admin and capability lifecycle orchestration.
- `src/stoa/routers/teacher_applications.py` and `src/stoa/routers/admin.py` — public application/activation and authenticated privileged lifecycle endpoints.
- `scripts/provision_production_admin.py` — first-admin/disaster-only guarded bootstrap with explicit binding/evidence.
- Focused identity, onboarding, curriculum, and bootstrap tests — replay, expiry, provider failure, immediate revocation, idempotency, and redaction evidence.

## Decisions Made

- Preserved the exact Plan 02 legacy adapter response shape. Its single top-level `capabilities` map is constructed only from fresh `Actor.current_grants`; curriculum code ignores every nested or claim-derived capability source.
- Required a verified access-token email claim for the public invitation-consumption endpoint, while the durable invitation stores only the token digest and binds the approved application version and normalized verified email.
- Treated provider group removal and global sign-out as defense in depth: local non-active status is written first and remains authoritative even when provider cleanup fails.
- Kept qualification documents entirely deferred: no blob field, upload path, scanning dependency, retention workflow, or review UI was introduced.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added a focused privileged identity command repository**

- **Found during:** Task 3 (routine administrator lifecycle)
- **Issue:** The plan required durable idempotent/conflict-checked routine privilege commands but named no repository artifact capable of owning their conditional state.
- **Fix:** Added `privileged_identity_repo.py` with immutable command input comparison and version-checked state transitions.
- **Files modified:** `src/stoa/db/repositories/privileged_identity_repo.py`, `src/stoa/services/privileged_identity_service.py`
- **Verification:** Duplicate identical provision returns idempotently without a second provider/binding mutation; conflicting or stale commands fail.
- **Committed in:** `1656be6`

---

**Total deviations:** 1 auto-fixed (1 missing critical).
**Impact on plan:** The repository is the minimum durable boundary required by the planned security invariant; it adds no external provider, document workflow, Phase 474 repair, or production mutation scope.

## Issues Encountered

- Adding an extra `current_grants` field to the legacy handler projection initially broke Plan 02's exact adapter contract. The implementation was corrected to preserve that response exactly and consume only its authoritative top-level capability map; the auth regression suite passes.
- No AWS credentials, network access, real Cognito mutation, or production write was attempted. The accepted unrelated Phase 474 full-suite DynamoDB credential baseline was not broadened or changed.

## User Setup Required

None - all provider behavior is injected in tests and no external service configuration or production mutation is authorized.

## Verification

- `.venv/bin/pytest -q tests/test_teacher_onboarding.py tests/test_identity_authorization.py tests/test_provision_production_admin.py tests/test_curriculum_ops.py`: **54 passed**.
- `.venv/bin/pytest -q tests/test_auth_security.py`: **36 passed**.
- `.venv/bin/python scripts/check_teacher_terminology.py --allowlist docs/security/tutor-term-allowlist.json`: **PASS**, exactly 11 historical/negative occurrences consumed.
- Ruff across `src/stoa`, the bootstrap script, and focused tests: **passed**.
- `git diff --check`: **passed**.

## Next Phase Readiness

- Ready for `472-05` central student-resource authorization to consume current scoped grants and local-first revocation facts.
- Plans 05–10 still own central policy, route migration/inventory, reconciliation, negative matrices, and P0 evidence. Phase 472 remains executing and is not complete.

## Self-Check: PASSED

- Every key created file exists and all three atomic task commits are present.
- Every task acceptance criterion and the plan-level verification command passed.
- Public teacher application/approval creates zero privilege; only same-verified-email one-time activation can reconcile teacher access.
- Routine privilege elevation/restoration requires explicit current manager capability and a durable approved command; bootstrap/root has no request-path bypass.
- No qualification document lifecycle, live provider call, network request, production mutation, or Phase 474 scope expansion occurred.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-14*
