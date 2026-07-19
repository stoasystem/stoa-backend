---
phase: 474-deterministic-verification-and-gated-delivery
plan: 09
subsystem: database
tags: [python, mypy, dynamodb, attachments, questions, usage-ledger, typing]

requires:
  - phase: 474-07
    provides: object-valued repository boundary and provider narrowing pattern
  - phase: 474-39
    provides: source-bound DynamoDB verification dependency
provides:
  - mypy-zero DynamoDB attachment, question, usage-ledger, and shared table boundary domain
  - validated object-valued provider records and per-operation runtime protocols
  - explicitly narrowed transaction, pagination, counter, and upload-part data
affects: [474-mypy-closure, attachments, questions, usage-accounting]

tech-stack:
  added: []
  patterns: [object-valued repository records, per-operation runtime protocols, validated provider responses]

key-files:
  created: []
  modified:
    - src/stoa/db/dynamodb.py
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/db/repositories/question_repo.py
    - src/stoa/db/repositories/usage_ledger_repo.py

key-decisions:
  - "DynamoDB records remain object-valued until exact string, integer, Decimal, mapping, and collection checks establish safe use."
  - "Per-operation runtime Protocols preserve minimal fake-table compatibility while rejecting provider objects that lack the requested operation."
  - "Attachment transactions validate nested maps and separate described high-level operations from raw DynamoDB transaction items without casts or ignores."

patterns-established:
  - "Provider response pattern: validate a string-keyed top-level mapping, then narrow each authority-bearing member before use."
  - "Table adapter pattern: runtime-check the smallest operation-specific Protocol instead of claiming one broad DynamoDB interface."

requirements-completed: [V9QUAL-04]

duration: 16 min
completed: 2026-07-19
---

# Phase 474 Plan 09: Attachment, Question, and Usage Repository Typing Summary

**Attachment, question, usage-ledger, and shared DynamoDB boundaries now pass focused mypy without `Any`, casts, ignores, or changes to authorization, privacy, idempotency, retry, fence, pagination, and stable-error behavior.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-07-19T17:10:51Z
- **Completed:** 2026-07-19T17:27:02Z
- **Tasks:** 1
- **Files modified:** 4

## Accomplishments

- Reduced the plan's focused mypy result from four attachment-repository diagnostics to zero diagnostics across all four declared source files.
- Replaced implicit and explicit `Any` boundaries with object-valued records, operation-specific runtime-checkable DynamoDB Protocols, and explicit provider-response validation.
- Narrowed attachment transactions, serialized attributes, batch results, upload coordinates and parts, counters, question usage, and pagination cursors before use.
- Preserved authorization, privacy, replay/idempotency, retry, account-fence, pagination, and stable-error behavior across 759 relevant regression tests.

## Task Commits

The task was committed atomically after its RED/GREEN verification cycle:

1. **Task 1 GREEN: type attachment, question, and usage repositories** - `16bfac5` (fix)

The RED gate was the plan's existing focused mypy command, which reproduced four diagnostics before implementation. Consistent with the preceding repository-typing plans, no new test file was added because this plan fixes a measured static-typing boundary and declares an exact four-source-file scope.

## Files Created/Modified

- `src/stoa/db/dynamodb.py` - Shared table lookup now returns an untrusted object boundary instead of leaking implicit `Any`.
- `src/stoa/db/repositories/attachment_repo.py` - Object-valued attachment records, operation-specific provider adapters, and validated transaction, batch, counter, cursor, and upload-part parsing.
- `src/stoa/db/repositories/question_repo.py` - Typed question records and response/count narrowing through minimal get, put, query, and update protocols.
- `src/stoa/db/repositories/usage_ledger_repo.py` - Typed usage records with validated provider items, counts, and pagination through minimal table protocols.

## Decisions Made

- Kept provider-returned records as `dict[str, object]` until runtime validation establishes the field's exact type and range.
- Used separate protocols for each DynamoDB operation so test fakes and real tables need only expose the method used by a code path.
- Rejected malformed top-level or nested provider mappings instead of coercing keys or values into trusted repository state.
- Preserved both high-level transaction-description fakes and low-level DynamoDB transaction serialization by explicitly separating and validating the two operation forms.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserved minimal question repository fake compatibility**
- **Found during:** Task 1 runtime regression verification
- **Issue:** The first narrow protocol draft grouped all question table methods into one interface, causing an update-only test fake to fail runtime protocol validation.
- **Fix:** Split the interface into operation-specific get, put, query, and update protocols so each code path validates only the capability it invokes.
- **Files modified:** `src/stoa/db/repositories/question_repo.py`
- **Commit:** `16bfac5`

## Issues Encountered

- The managed filesystem denied `.git/index.lock` creation during the first staging attempt. The same narrow four-file Git operation was rerun with approved repository permission; no hook was bypassed and no reset, stash, clean, or unrelated path was used.
- Replacing the shared DynamoDB table's implicit `Any` result exposes downstream caller errors that were previously masked. The exact full-scope command now reports 630 errors in 88 files, while all four Plan 474-09 targets remain at zero; these downstream diagnostics remain release-blocking for later coherent typing plans.
- The broader runtime gate reports one existing Starlette test-client deprecation warning. All 759 tests pass and the warning is outside this plan's four-file scope.

## Known Stubs

None. Empty dictionaries and lists are bounded response, transaction, or pagination accumulators; optional `None` values are explicit query and transition outcomes rather than UI placeholders or unwired data.

## User Setup Required

None - no external service configuration required.

## Verification

- RED: focused mypy reproduced 4 errors in `attachment_repo.py` before implementation.
- Plan command: focused mypy passed with no issues in all 4 source files; 259 named attachment, question, and usage tests passed; focused Ruff passed.
- Broader relevant regression: 759 tests passed across 27 attachment, conversation, learning, moderation, notification, retention, reporting, student, teacher, and usage test modules.
- Exact full scope: 229 source files checked; no diagnostics remain in the four Plan 474-09 targets. The remaining 630 diagnostics in 88 downstream files stay release-blocking for subsequent typing plans.
- Suppression scan found no `Any`, `cast(`, `type: ignore`, mypy weakening, skip, or xfail in the four target files.
- `git diff --check` passed; task commit contains no deletions; backend was clean after the task commit.
- Stub and threat-surface scans passed. No endpoint, authentication mechanism, provider call, file-access boundary, schema, dependency, or production operation was introduced.
- Production infrastructure, deployment, smoke, and rollback remained exact `NOT RUN`.

## Next Phase Readiness

- Later typing plans can narrow the newly visible downstream callers of the shared object-valued DynamoDB table boundary without reintroducing masking types.
- Plan 474-26 remains intentionally incomplete: no summary was created, its skipped Linux ARM64 boot-smoke issue was not revisited, and its infra quarantine was not modified.

## Self-Check: PASSED

- All four declared target files and this summary exist.
- Task commit `16bfac5` exists and contains no tracked-file deletions.
- Task acceptance, plan verification, broader relevant regression, suppression scan, stub scan, diff check, and threat-surface scan passed.
- Plan 474-26 remains incomplete and has no summary.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-19*
