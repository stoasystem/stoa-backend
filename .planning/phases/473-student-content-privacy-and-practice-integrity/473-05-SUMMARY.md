---
phase: 473-student-content-privacy-and-practice-integrity
plan: 05
subsystem: practice-privacy
tags: [fastapi, pydantic, dynamodb, practice, curriculum, authorization]

requires:
  - phase: 473-01
    provides: Answer-free preview, durable-attempt result, hint, and privileged-answer contracts
provides:
  - Typed answer-free projections for every student practice and curriculum read family
  - Immutable owner-scoped persistence for correct and incorrect student attempts
  - Write-before-reveal answer results and owner-only result reads
  - Explicitly approved directional hints with answer and explanation guards
affects: [473-06, 473-07, 475-attempt-consistency, 478-mobile-practice]

tech-stack:
  added: []
  patterns:
    - Typed allowlist projections shared by legacy practice and curriculum routes
    - Owner-scoped DynamoDB attempt keys with conditional immutable puts
    - Durable receipt required before answer-bearing result serialization

key-files:
  created:
    - src/stoa/services/practice_projection_service.py
  modified:
    - src/stoa/models/practice.py
    - src/stoa/db/repositories/practice_repo.py
    - src/stoa/services/curriculum_service.py
    - src/stoa/routers/practice.py
    - src/stoa/security/route_inventory.py
    - docs/security/route-authorization-inventory.json

key-decisions:
  - "Student overview, path, lesson, catalog, exercise, and mistake-preview content is projected from answer-free allowlists; includeAnswers is never a student contract switch."
  - "Every correct or incorrect answer is conditionally persisted under the student owner before standard answers, explanations, or result feedback are constructed."
  - "Pre-submit hints are returned only when explicitly approved and mechanically free of normalized answer, explanation, and feedback content."

patterns-established:
  - "Preview projection: sensitive source dictionaries enter one typed allowlist before serialization, never build-then-pop redaction."
  - "Attempt result: POST and GET share one result builder fed by a durable owner receipt."

requirements-completed: [V9PRIV-03]

duration: 17 min
completed: 2026-07-16
---

# Phase 473 Plan 05: Answer-free previews and recorded-attempt results Summary

**All student practice and curriculum previews are structurally answer-free, while standard answers and explanations unlock only after an immutable owner attempt is durably recorded.**

## Performance

- **Duration:** 17 min
- **Started:** 2026-07-16T10:35:00Z
- **Completed:** 2026-07-16T10:52:25Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments

- Replaced legacy answer-bearing challenge and curriculum builders with typed challenge, lesson, exercise, and curriculum-detail allowlists shared across overview, path, lesson, catalog, exercise, and mistake-preview responses.
- Added conditional all-attempt persistence containing owner, submitted answer, correctness, content coordinates, and timestamp; both correct and incorrect submissions now receive durable receipts.
- Added an owner-resolved attempt result endpoint and made POST answer results serialize only after persistence succeeds; write failures expose one stable answer-free 503.
- Removed generated/unreviewed hint fallbacks and return content only for explicitly approved directional hints that do not contain normalized answer, explanation, or feedback material.
- Registered `attemptId` as a governed practice identifier and regenerated the checked runtime/OpenAPI authorization inventory.

## Task Commits

Each task was committed atomically:

1. **Task 1: Migrate all student practice and curriculum reads to answer-free projections** - `f989691` (feat)
2. **Task 2: Persist every attempt before returning answer-bearing result and safe hints** - `b90bb5c` (feat)
3. **Task 2 regression fix: Register attempt result authorization inventory** - `0c01f87` (fix)

## Files Created/Modified

- `src/stoa/services/practice_projection_service.py` - Central preview, result, and directional-hint projections.
- `src/stoa/models/practice.py` - Typed challenge, lesson, exercise, curriculum, submission, hint, and result contracts.
- `src/stoa/db/repositories/practice_repo.py` - Immutable all-attempt put/get/list operations with legacy mistake read compatibility.
- `src/stoa/services/curriculum_service.py` - Answer-free student lesson and exercise builders without answer switches.
- `src/stoa/services/adaptive_learning_service.py` - Migrated the internal preview caller to the answer-free exercise builder.
- `src/stoa/routers/practice.py` - Answer-free read routes, durable submit/result flow, safe hints, and answer-free mistakes.
- `src/stoa/security/route_inventory.py` - Canonical `attemptId` to practice-resource authorization mapping.
- `docs/security/route-authorization-inventory.json` - Regenerated checked inventory containing the owner-result route.
- `tests/test_practice.py` - Persistence ordering, failure redaction, result ownership, and hint safety coverage.
- `tests/test_practice_privacy.py` - Recursive route-family, OpenAPI, immutable receipt, and authorization-inventory coverage.
- `tests/test_curriculum_rollout.py` - Curriculum answer-toggle and nested explanation privacy coverage.
- `tests/test_curriculum_analytics.py` - All-attempt receipt compatibility for analytics and usage tests.

## Decisions Made

- Unknown student query parameters such as `includeAnswers=true` are harmlessly ignored; there is no student answer-bearing builder or response-field switch.
- Attempt primary keys include the verified student owner, so foreign and random attempt IDs resolve through the same concealed not-found path without a cross-owner lookup.
- Historical wrong-only rows remain readable for Phase 475 reconciliation, while all new attempts use the immutable owner-scoped contract and retain submitted answers.
- Plan 06 remains the sole owner of separately authorized assignment-scoped teacher/global-admin answer reads; this plan grants no mutation or privileged read authority.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Migrated adaptive preview caller after removing answer flags**
- **Found during:** Task 1
- **Issue:** `adaptive_learning_service` called the curriculum builder with the removed `include_answer_key` switch.
- **Fix:** Migrated that caller to the same unconditional answer-free exercise preview contract.
- **Files modified:** `src/stoa/services/adaptive_learning_service.py`
- **Verification:** Adaptive learning plus practice/curriculum regression suite passed.
- **Committed in:** `f989691`

**2. [Rule 2 - Missing Critical] Registered attempt identifiers in authorization inventory**
- **Found during:** Plan-level full regression
- **Issue:** The new owner-result route was authorized at runtime, but `attemptId` was not yet a canonical governed identifier and the checked inventory was stale.
- **Fix:** Mapped `attemptId` to the practice resource type, asserted the executable authorization projection, and regenerated checked JSON.
- **Files modified:** `src/stoa/security/route_inventory.py`, `docs/security/route-authorization-inventory.json`, `tests/test_practice_privacy.py`
- **Verification:** Route inventory suite passed 56 tests; the full suite passed 1176 tests.
- **Committed in:** `0c01f87`

---

**Total deviations:** 2 auto-fixed (1 blocking compatibility issue, 1 missing critical authorization-inventory guard).
**Impact on plan:** Both fixes preserve established integrations and make the planned endpoint fail closed in generated authorization evidence; no scope expansion or privileged access was added.

## Issues Encountered

- The first Task 2 commit attempt could not create `.git/index.lock` in the sandbox. The same individually staged commit was rerun with repository write approval; hooks remained enabled and passed.
- The first full suite run exposed only the stale authorization inventory snapshot (1174 passed, 1 failed). After the governed identifier fix and regeneration, the entire suite passed.

## Verification

- Task 1 focused preview gate: `19 passed, 13 deselected`.
- Task 2 focused attempt/result/hint gate: `34 passed, 2 deselected`.
- Exact plan suite (`test_practice.py`, `test_practice_privacy.py`, `test_curriculum_rollout.py`): `41 passed`.
- Related practice/curriculum/adaptive/analytics regression: `74 passed`.
- Authorization inventory and practice privacy gate: `56 passed`.
- Full Python regression: `1176 passed in 30.98s` (stated baseline: 1163 passed).
- Targeted Ruff and `git diff --check`: PASS.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 473-06 can add the separate assignment-scoped teacher/global-admin answer-read contract without changing student previews or granting curriculum mutation.
- Phase 475 can converge attempt usage/analytics transactions and reconcile historical unknown submitted answers on top of the immutable attempt repository contract.
- No blocker remains for Plan 473-05.

## Self-Check: PASSED

- Created projection service exists and all listed production commits are present.
- Every task acceptance criterion and plan-level verification command passes.
- Full regression exceeds the supplied green baseline without weakening production Settings validation.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-16*
