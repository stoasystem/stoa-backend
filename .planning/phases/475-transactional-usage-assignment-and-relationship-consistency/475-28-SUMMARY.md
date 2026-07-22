---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 28
subsystem: database
tags: [dynamodb, notifications, account-deletion, cas, identity-scrub]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 25
    provides: closed cross-account identity discovery and two-clean-epoch quiescence
  - phase: 473-student-content-privacy-and-practice-integrity
    provides: notification deletion branch, account fences, and retained delivery evidence semantics
provides:
  - closed direct actor and reviewed metadata identity discovery for notification rows
  - exact-CAS reference-only scrub that preserves recipient-owned delivery and effect evidence
  - branch-level proof for CAS retry, late-row reset, and two later strong clean epochs
affects: [account-deletion, notification-delivery, CR-10, V9DATA-07]

tech-stack:
  added: []
  patterns: [entity-scoped identity registry, reference-only CAS scrub, strong clean-epoch quiescence]

key-files:
  created:
    - tests/test_phase475_deletion_notification_identity_scrub.py
  modified:
    - src/stoa/db/repositories/notification_repo.py

key-decisions:
  - "Owner matches retain the existing full notification tombstone path; foreign identity references use a separate narrow scrub."
  - "Reference cleanup binds the deletion fence, exact row identity/schema, event version, status, direct actor match when present, and the complete metadata snapshot before mutation."
  - "Only direct actor_id and reviewed top-level metadata actor_id, teacher_id, and parent_id values are removed; recipient, target, effect, status, and delivery receipt fields remain unchanged."

patterns-established:
  - "Notification reference scrub: classify from a closed entity/field registry, then remove only exact deleting-identity fields under one fenced CAS."
  - "Notification quiescence: any match, CAS loss, or late row resets progress before two later complete strong clean epochs."

requirements-completed: [V9DATA-07]

duration: 4 min
completed: 2026-07-22
---

# Phase 475 Plan 28: Notification Identity Reference Scrub Summary

**Recipient-owned notifications now remove deleting actor, teacher, and parent references through a deletion-fenced exact CAS while preserving delivery/effect evidence and requiring two later strong clean epochs.**

## Performance

- **Duration:** 4 min (continuation session)
- **Started:** 2026-07-22T09:34:57Z
- **Completed:** 2026-07-22T09:38:24Z
- **Tasks:** 1
- **Files modified:** 2 planned files

## Accomplishments

- Extended strong notification discovery with a closed exact classifier for direct `actor_id` and reviewed metadata `actor_id`, `teacher_id`, and `parent_id` references.
- Split deletion handling so owner rows still use full tombstones while cross-account references remove only the deleting identity and increment `event_version`.
- Bound reference cleanup to the permanent deletion fence and exact PK/SK, entity/schema, version, status, direct identity where applicable, and complete metadata snapshot.
- Proved one CAS race preserves a concurrent metadata write, a late notification resets progress, and completion occurs only after two later strong clean epochs.

## TDD Cycle

- **RED:** `3a90a99` added the branch-level proof and failed before reference-aware discovery/scrub existed.
- **GREEN:** `96dea3f` implemented closed discovery and fenced narrow cleanup; focused and inherited notification/delivery suites pass.
- **REFACTOR:** No production refactor was required; the test fake received explicit runtime narrowing so the planned mypy gate remained clean.

## Task Commits

1. **RED: Add failing notification identity scrub proof** - `3a90a99` (test)
2. **GREEN: Scrub notification identity references** - `96dea3f` (feat)

## Files Created/Modified

- `tests/test_phase475_deletion_notification_identity_scrub.py` - Real deletion-branch proof for discovery, malformed metadata, CAS retry, preserved evidence, late-row reset, and two clean epochs.
- `src/stoa/db/repositories/notification_repo.py` - Closed identity-reference registry, reference-aware scan routing, owner/reference scrub split, and exact CAS cleanup.

## Decisions Made

- Kept the existing owner tombstone contract unchanged because recipient-owned foreign-reference rows must preserve durable delivery facts rather than inherit owner deletion minimization.
- Used complete metadata equality in the DynamoDB condition, which is stronger than a digest-only comparison while the canonical digest remains available to repository test hooks.
- Restricted metadata matching to reviewed top-level identity keys; arbitrary nested payload values and substring matches remain outside the classifier.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Narrowed provider-shaped values in the branch test fake**
- **Found during:** Task 1 GREEN verification
- **Issue:** Targeted mypy rejected direct `int()` and `dict()` construction from `object`-typed fake-row values.
- **Fix:** Added explicit integer and mapping runtime assertions before simulating the concurrent CAS write.
- **Files modified:** `tests/test_phase475_deletion_notification_identity_scrub.py`
- **Verification:** Targeted mypy, Ruff, focused pytest, and inherited regressions all pass.
- **Committed in:** `96dea3f`

**2. [Rule 1 - Bug] Preserved the SDK-reported project progress percentage**
- **Found during:** Plan metadata closeout
- **Issue:** `state.update-progress` reported 58% but wrote 20% into `STATE.md` while recalculating disk summaries.
- **Fix:** Restored the reported 58% value while retaining the SDK's completed-plan count and session updates.
- **Files modified:** `.planning/STATE.md`
- **Verification:** `STATE.md` records 117/201 completed plans and 58%, matching the SDK result.
- **Committed in:** Plan metadata commit

---

**Total deviations:** 2 auto-fixed (1 blocking type-boundary correction, 1 state-update bug).
**Impact on plan:** The test correction preserves RED behavior and adds no production scope; the metadata correction prevents a false project-progress regression.

## Issues Encountered

- Expanded Ruff over `tests/test_phase473_notification_deletion.py` reports a pre-existing unused `account_deletion_repo` import at line 10. The inherited suite passes, planned files pass Ruff, and the unchanged out-of-scope item is recorded in `deferred-items.md` without modification.

## Verification

- Focused Plan 475-28 node — 1 passed.
- Focused plus inherited notification deletion and delivery recovery suites — 18 passed.
- Ruff over both planned files — passed.
- Mypy over both planned files — passed with no issues.
- `git diff --check HEAD~1..HEAD` — passed.
- Normal Git hooks ran on the GREEN commit; no verification bypass was used.

## User Setup Required

None - no package installation, credentials, provider calls, deployments, or external configuration are required.

## Known Stubs

None. Empty collections in the proof are bounded transaction/result accumulators or deliberate clean-page state; no runtime data source remains unwired.

## Next Phase Readiness

- CR-10 notification actor/metadata cleanup is complete and ready for the remaining Phase 475 gap-closure plans.
- Live AWS, provider, Web, native, billing, and deployment work remains outside this plan.

## Self-Check: PASSED

- Both planned files and this summary exist.
- RED commit `3a90a99` and GREEN commit `96dea3f` exist in Git history in the required order.
- Focused acceptance proof, inherited notification/delivery regressions, Ruff, mypy, diff check, stub scan, and threat-surface scan passed.
- No new endpoint, authorization path, file-access boundary, dependency, or schema was introduced beyond the plan's notification metadata threat model.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
