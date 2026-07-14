---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 03
subsystem: security
tags: [registration, cognito, teacher, terminology, semantic-gate]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    plan: 01
    provides: canonical roles, immutable Actor, and stable fail-closed identity errors
provides:
  - Exact student/parent-only public registration command validated before provider or repository access
  - Canonical teacher-only API and repository surface with no legacy route compatibility
  - Executable semantic terminology gate with exact negative/historical fixture accounting
affects: [472-04, 472-05, 472-06, 472-07, 472-08, 472-09, 472-10, 478]

tech-stack:
  added: []
  patterns: [closed public registration command, persisted confirmation provenance, canonical teacher contract, exact semantic allowlist]

key-files:
  created:
    - scripts/check_teacher_terminology.py
    - docs/security/tutor-term-allowlist.json
  modified:
    - src/stoa/models/user.py
    - src/stoa/routers/auth.py
    - src/stoa/routers/teachers.py
    - src/stoa/main.py
    - src/stoa/security/identity.py
    - tests/test_auth_security.py
    - tests/test_teacher_availability.py
    - tests/test_teacher_terminology_gate.py

key-decisions:
  - "Public self-service registration accepts only exact student or parent roles and persists command provenance that confirmation must revalidate."
  - "All public auth flows use one non-privileged app client and never infer, repair, or select privilege from caller role or profile/email fallback."
  - "Teacher is the sole active teacher-role vocabulary: no compatibility route, alias, normalization, mirrored response, or dual-write remains."
  - "Historical terminology is permitted only in exact named negative-input or reconciliation fixtures; every expected count is consumed and stale entries fail closed."

patterns-established:
  - "Public privilege barrier: validation occurs before Cognito construction, sign-up, group mutation, or profile persistence."
  - "Terminology gate: source, tests, scripts, mobile contracts, and filenames are scanned semantically, with mutation tests proving active-contract detection."

requirements-completed: [V9AUTH-01]

duration: 83 min
completed: 2026-07-14
---

# Phase 472 Plan 03: Public privilege barrier and canonical teacher terminology Summary

**Public account creation is now structurally limited to student/parent commands, while the active API/runtime vocabulary has one teacher role, one `/teachers` surface, and an exact fail-closed semantic gate.**

## Performance

- **Duration:** 83 min
- **Started:** 2026-07-14T20:42:00Z
- **Completed:** 2026-07-14T22:05:00Z
- **Tasks:** 3
- **Files modified:** 41

## Accomplishments

- Replaced permissive router-local registration strings and aliases with an exact domain model that rejects privileged, unknown, variant, nested, and extra role inputs before any provider or database call.
- Bound confirmation, resend, and password flows to persisted public self-service provenance and removed caller-selected privileged clients, role repair, email fallback, and profile inference from public auth paths.
- Consolidated availability, dispatch, assistance, AI-tool, help-request, notes, and stats behavior under `/teachers`, deleted the legacy router, and renamed repository, model, response, and positive-fixture contracts.
- Renamed active service, curriculum, notification, websocket, pilot, adaptive, test, and mobile terminology to teacher without retaining aliases or mirrored values.
- Added an executable gate that accounts for exactly 11 historical/negative occurrences, rejects stale or broad exemptions, scans filenames, and proves six active-contract mutation categories fail.

## Task Commits

Each task was committed atomically:

| Task | Description | Commit |
| --- | --- | --- |
| 472-03-01 | Close public privilege registration and confirmation paths | `a65108b` |
| 472-03-02 | Consolidate the canonical teacher API surface | `7d11610` |
| 472-03-03 | Rename active contracts and enforce the semantic terminology gate | `816a0bb` |

## Files Created/Modified

- `src/stoa/models/user.py` — exact student/parent public registration contract with forbidden extras.
- `src/stoa/routers/auth.py` — non-privileged public client and persisted command-bound lifecycle flows.
- `src/stoa/routers/teachers.py` — complete canonical teacher availability, queue, assistance, tool, and note surface.
- `src/stoa/routers/tutors.py` — deleted; no compatibility router remains.
- `src/stoa/main.py` — registers only the canonical teacher router.
- `src/stoa/db/repositories/user_repo.py` — canonical teacher availability mutation name.
- `src/stoa/security/identity.py` — historical role values remain outside the closed canonical vocabulary and deny.
- `scripts/check_teacher_terminology.py` — exact semantic source/test/script/mobile and filename scanner.
- `docs/security/tutor-term-allowlist.json` — narrow symbol-level negative/historical occurrence inventory.
- `tests/test_teacher_terminology_gate.py` — exact-usage, stale-entry, and active-contract mutation coverage.
- `tests/test_teacher_availability.py` — canonical positive teacher contract and removed-route 404 evidence.
- Active adaptive, admin, AI, curriculum, moderation, notification, dispatch, pilot, usage, websocket, mobile, and focused test contracts — canonical teacher terminology.

## Decisions Made

- Confirmation trusts only the already persisted `public_self_service` registration command and exact approved registration role; it does not reconstruct authority from a new payload.
- Public authentication uses a single non-privileged Cognito client even when privileged app clients remain configured for non-public workflows.
- Historical role strings are rejected by closed enums/group resolution and remain only as explicit negative or future reconciliation evidence, never as accepted aliases.
- The terminology gate uses exact file, test symbol, literal, purpose, and count tuples. Production exemptions, glob paths, module-level exemptions, duplicates, and unused entries are invalid.

## Deviations from Plan

None - the plan was executed as specified.

## Issues Encountered

- The broader adaptive-learning suite still has the accepted unrelated Phase 474 DynamoDB/AWS credential baseline: 11 tests attempted unstubbed DynamoDB access and failed with `NoCredentialsError` (one downstream empty-selection assertion shares that baseline). No network, credentials, or production provider was used, and all Plan 472-03 locked verification commands passed.
- Future Plan 472-05 reconciliation fixtures still import their not-yet-implemented module; they were retained as historical evidence and were not treated as Plan 472-03 scope.

## User Setup Required

None - no external credentials, provider calls, or production mutation are required.

## Verification

- `.venv/bin/pytest -q tests/test_auth_security.py tests/test_auth_account_lifecycle.py -k 'register or confirmation or role or privilege'`: **19 passed, 40 deselected**.
- `.venv/bin/pytest -q tests/test_teacher_availability.py tests/test_teacher_dispatch.py tests/test_ai_teacher_tools.py`: **17 passed**.
- `.venv/bin/python scripts/check_teacher_terminology.py --allowlist docs/security/tutor-term-allowlist.json`: **PASS**, exactly **11** allowlisted occurrences used and no stale entries.
- Task 3 locked seven-file suite: **91 passed**.
- Additional non-adaptive identity, curriculum, parent, and teacher SLA suite: **129 passed**.
- Targeted Ruff across all plan Python surfaces: **passed**.
- `git diff --check`: **passed**.

## Next Phase Readiness

- Ready for `472-04` to add a separate no-privilege teacher candidacy/application workflow outside public registration.
- Plans 04–10 still own privileged onboarding, capability lifecycle, central resource policy, route migration, reconciliation review, and P0 evidence. Phase 472 remains executing.

## Self-Check: PASSED

- All required artifacts exist, the legacy router is deleted, and `/tutors` is absent.
- Three atomic task commits are present.
- Every locked task and plan verification command passed without AWS/network access.
- The exact milestone name is unchanged and Phase 472 is not marked complete.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-14*
