---
phase: 473-student-content-privacy-and-practice-integrity
plan: 23
subsystem: saved-attachment-lifecycle
tags: [fastapi, dynamodb-consistent-read, s3-versioning, load-once-authorization, streaming]
requires:
  - phase: 473-22
    provides: exhaustive retention fences, exact-version deletion, and quota reconciliation
provides:
  - coordinate-free owner list, detail, download, and delete APIs for saved attachments
  - exact immutable verified download spooling with provider-body closure
  - typed attachment-only purge progress for the Plan 473-29 account purge orchestrator
affects: [473-27, 473-29, 473-35, 478-mobile-integration]
tech-stack:
  added: []
  patterns:
    - load-once AuthorizedResource dependencies for owner-scoped attachment routes
    - exact-version verification into a bounded spool before client streaming
key-files:
  created:
    - tests/test_phase473_saved_attachments.py
  modified:
    - src/stoa/models/attachment.py
    - src/stoa/security/attachment_errors.py
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/services/attachment_service.py
    - src/stoa/routers/files.py
    - docs/security/route-authorization-inventory.json
key-decisions:
  - Owner routes authorize one authoritative loaded attachment resource and conceal missing or foreign identifiers identically.
  - Downloads verify the exact immutable object version, ETag, length, and SHA-256 before streaming and always close the provider body.
  - Attachment purge reports independent typed progress under the existing account fence and cannot finalize that fence.
patterns-established:
  - Saved attachment APIs expose opaque IDs and safe presentation metadata without provider coordinates.
  - Destructive attachment work remains reference-safe and reports retryable debt instead of overstating completion.
requirements-completed: [V9PRIV-01, V9PRIV-02]
duration: 15 min
completed: 2026-07-17
---

# Phase 473 Plan 23: Saved Attachment Access and Durable Purge Branch Summary

Coordinate-free saved-attachment owner APIs now use authoritative load-once authorization, verified exact-version downloads, reference-safe deletion, and a typed purge branch that preserves account-fence ownership.

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-17T20:24:56Z
- **Completed:** 2026-07-17T20:39:38Z
- **Tasks:** 3
- **Files modified:** 7

## Accomplishments

- Added contract coverage for saved-attachment listing, detail, download, deletion, authorization concealment, filename safety, body closure, and purge progress.
- Implemented authoritative owner attachment reads plus immutable object verification into a bounded spool before any client bytes are streamed.
- Added reference-safe deletion and a typed attachment purge branch that accepts an existing account fence generation but never finalizes the account fence.
- Exposed four centrally classified owner routes without leaking bucket, object key, version ID, or internal storage coordinates.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add failing saved attachment lifecycle contracts** - `3a422aa` (test)
2. **Task 2: Implement owner attachment services and purge branch** - `9d10033` (feat)
3. **Task 3: Expose authorized saved attachment routes** - `4b9f2fe` (feat)

## Files Created/Modified

- `tests/test_phase473_saved_attachments.py` - Owner lifecycle, safe download, deletion, concealment, and purge contracts.
- `src/stoa/models/attachment.py` - Coordinate-free attachment projections and typed purge progress models.
- `src/stoa/security/attachment_errors.py` - Structured attachment-in-use failure with safe recovery action.
- `src/stoa/db/repositories/attachment_repo.py` - Authoritative attachment enumeration plus account upload cleanup, tombstone, and quota helpers.
- `src/stoa/services/attachment_service.py` - Owner access, exact-version download verification, reference-safe delete, and attachment purge branch.
- `src/stoa/routers/files.py` - Four load-once authorized saved-attachment routes.
- `docs/security/route-authorization-inventory.json` - Regenerated classifications for the new route surface.

## Decisions Made

- Owner attachment routes use one authoritative raw row to build `AuthorizedResource`; downstream handlers reuse that same loaded resource.
- Download responses are created only after exact version, ETag, length, and SHA-256 verification succeeds, and provider response bodies are closed on every path.
- The attachment purge branch exposes status, cursors, debt, and quiescence under the caller's fence generation while leaving final account-fence completion to the later orchestrator.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Regenerated the checked authorization inventory**

- **Found during:** Task 3
- **Issue:** Adding four routes made the checked route-authorization inventory stale, which blocked the mandatory inventory validation gate.
- **Fix:** Ran the project inventory generator and committed the resulting route classifications with the implementation.
- **Files modified:** `docs/security/route-authorization-inventory.json`
- **Verification:** Route authorization gate passed with 77 tests.
- **Commit:** `4b9f2fe`

## Issues Encountered

- The Task 2 example command contains two `-k` options; pytest honors only the final expression, so the literal command deselected the intended tests. The equivalent focused commands were run separately, followed by the full inherited attachment gate (`245 passed, 1 deselected`). This required no product change.

## Verification

- RED gate: `17 failed, 5 passed` before implementation.
- Task 2 attachment gate: `245 passed, 1 deselected`.
- Task 3 route and inventory gate: `77 passed`.
- Plan-level gate: `311 passed` across saved attachments, inherited file/security coverage, route authorization inventory, and terminology tests.
- Ruff passed for every changed Python file.
- `git diff --check`, recursive response-schema coordinate denial, route inventory validation, privacy guards, and tutor-terminology scan all passed.
- Real S3 and deployed-provider checks were not required by this plan and were not run.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 473-29 can compose the typed attachment purge branch into the durable account purge orchestrator.
- The coordinate-free owner API is ready for later retention and mobile-integration plans.
- No unresolved blockers.

## Self-Check: PASSED

- All seven created or modified deliverable paths exist.
- Task commits `3a422aa`, `9d10033`, and `4b9f2fe` exist in repository history.
- All mandatory plan-level verification gates passed.
