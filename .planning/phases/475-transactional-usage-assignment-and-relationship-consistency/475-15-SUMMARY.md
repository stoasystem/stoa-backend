---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 15
subsystem: api
tags: [sha256, idempotency, dynamodb, usage-ledger, privacy]

requires:
  - phase: 475-transactional-usage-assignment-and-relationship-consistency
    plan: 14
    provides: required bounded caller-owned question submission identity
provides:
  - student-bound opaque question command identity derived at the API boundary
  - digest-only command and usage-ledger durable schema
  - arbitrary-canary non-disclosure proof across storage, responses, and diagnostics
affects: [475-19-question-replay-integrity, 475-44-coverage-registry, V9DATA-01]

tech-stack:
  added: []
  patterns: [domain-separated length-prefixed sha256, digest-only durable coordinates, strict schema-v2 replay classification]

key-files:
  created: []
  modified:
    - src/stoa/db/repositories/question_submission_repo.py
    - src/stoa/services/usage_ledger_service.py
    - src/stoa/routers/questions.py
    - tests/test_phase475_question_admission.py
    - tests/test_phase475_question_replay.py
    - tests/test_questions.py
    - tests/test_phase475_question_reconciliation.py
    - tests/test_usage_ledger.py

key-decisions:
  - "Question command identity is a lowercase SHA-256 over a domain tag plus length-prefixed canonical student ID and exact validated caller key bytes."
  - "The one student-bound digest is the command ID, command SK suffix, ledger event ID/SK suffix, and persisted idempotency digest; raw caller text has no durable compatibility path."
  - "Question command schema v2 rejects v1/raw or malformed rows before payload comparison and never returns their stored coordinates."

patterns-established:
  - "Question route boundary: body.idempotency_key is read exactly once into question_submission_command_digest; all later collaborators receive only the digest."
  - "Question replay classification validates entity, schema, owner, digest, command ID, status, and question ID before preserving independent payload-mismatch behavior."

requirements-completed: [V9DATA-01]

duration: 15 min
completed: 2026-07-22
---

# Phase 475 Plan 15: Opaque Question Command Identity Summary

**Question submission now converts exact caller-owned replay text into one student-bound opaque digest at the API boundary, with only that digest reaching command rows, ledger rows, replay coordinates, responses, or diagnostics.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-22T08:52:29Z
- **Completed:** 2026-07-22T09:07:02Z
- **Tasks:** 1
- **Files modified:** 8

## Accomplishments

- Added a domain-separated, length-prefixed SHA-256 command identity over canonical student ID and exact caller key bytes, producing one validated lowercase 64-hex digest.
- Moved hashing to the question route boundary and changed repository and question-ledger APIs to accept only validated digests.
- Upgraded question commands to schema v2 with `idempotency_digest`; command SK, `command_id`, ledger SK, `event_id`, and ledger idempotency metadata all share the same opaque digest.
- Made preflight and post-reservation replay use strict repository classification, rejecting malformed and legacy raw-key rows without projecting their coordinates.
- Added arbitrary email/question canaries covering captured transaction operations, command/ledger rows, public response bodies, exceptions, private event payloads, and logs.
- Preserved deterministic same-key replay and independent exact-payload mismatch behavior, including cross-student digest separation.

## Task Commits

Each TDD gate was committed atomically:

1. **RED: Add failing opaque question identity proofs** - `2d37c4c` (test)
2. **GREEN: Persist opaque question command identities** - `092d80a` (feat)

## Files Created/Modified

- `src/stoa/db/repositories/question_submission_repo.py` - Student-bound digest derivation, strict digest validation, schema-v2 command construction/classification, and digest-only replay/reconciliation keys.
- `src/stoa/services/usage_ledger_service.py` - Digest-only question event builder/reader/writer and opaque question event response metadata.
- `src/stoa/routers/questions.py` - One-time API-boundary hashing and digest-only preflight, ledger, and admission calls.
- `tests/test_phase475_question_admission.py` - Digest domain separation, strict legacy rejection, transaction/row arbitrary-canary scan, replay, mismatch, and quota proof.
- `tests/test_phase475_question_replay.py` - Source/runtime proof that raw caller text crosses once and is absent from responses, logs, and private diagnostics.
- `tests/test_questions.py` - Direct route fixtures and ledger assertions migrated to schema-v2 opaque commands.
- `tests/test_phase475_question_reconciliation.py` - Reconciliation fixtures migrated to digest-only command/ledger coordinates.
- `tests/test_usage_ledger.py` - Direct question-ledger fixtures migrated to validated digest inputs.

## Decisions Made

- Used unkeyed SHA-256 because this identity needs deterministic reconstruction rather than authentication; student binding, explicit domain separation, and length framing prevent cross-owner and field-boundary collapse.
- Made the digest itself the command and ledger event identity. The digest already binds the student, so prefixing it with raw owner/request material would add disclosure surface without identity value.
- Bumped only the question command schema to v2. Generic non-question ledger events retain their existing contract, while question events expose `idempotencyDigest` rather than a misleading raw-key field.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Migrated directly affected inherited replay and ledger fixtures**
- **Found during:** Task 1 expanded regression verification
- **Issue:** Existing question route, reconciliation, and usage-ledger tests still constructed schema-v1 raw-key rows or called question-ledger helpers with raw keys, so they no longer represented the required durable contract.
- **Fix:** Migrated only those directly affected fixtures and assertions to derive and use the opaque digest while preserving their original replay, reversal, quota, attachment, and support-summary assertions.
- **Files modified:** `tests/test_questions.py`, `tests/test_phase475_question_reconciliation.py`, `tests/test_usage_ledger.py`
- **Verification:** The expanded six-module regression passes 74 tests and Ruff passes all directly changed source/test files.
- **Committed in:** `092d80a`

---

**Total deviations:** 1 auto-fixed (1 missing critical regression migration).
**Impact on plan:** Test-only fixture migration preserves directly affected coverage and adds no product scope.

## Issues Encountered

- An optional combined mypy probe found eight existing diagnostics on unchanged lines in `usage_ledger_service.py` and `questions.py`; `question_submission_repo.py` itself is clean. Mypy was not a Plan 475-15 gate, and the unrelated pre-existing diagnostics were not modified.

## Verification

- `.venv/bin/python -m pytest -q tests/test_phase475_question_admission.py tests/test_phase475_question_replay.py -k 'privacy or idempotency or replay or mismatch'` - 14 passed, 10 deselected.
- `.venv/bin/ruff check src/stoa/db/repositories/question_submission_repo.py src/stoa/services/usage_ledger_service.py src/stoa/routers/questions.py tests/test_phase475_question_admission.py tests/test_phase475_question_replay.py` - passed.
- Expanded direct regression across question admission/replay, question routes, learning expansion, question reconciliation, and usage ledger - 74 passed.
- Acceptance matrix for stable/cross-student digest, arbitrary canary, legacy rejection, changed-payload mismatch, and lost-response replay - 6 passed.
- Expanded Ruff across all eight modified files - passed.
- `git diff --check` - passed.

## User Setup Required

None - no dependency, credential, service, migration command, or deployment change is required.

## Known Stubs

None.

## Next Phase Readiness

- Plan 475-19 can enforce full replay ownership/integrity against the schema-v2 digest command without handling raw caller keys.
- Plan 475-44 can register CR-08 against dynamic arbitrary-canary evidence rather than a fixed denylist.

## Self-Check: PASSED

- All eight modified implementation/test files exist.
- RED commit `2d37c4c` and GREEN commit `092d80a` exist in repository history with no tracked deletions.
- Every task acceptance criterion, plan verification command, direct regression, privacy canary node, Ruff gate, and diff check passes.
- The only remaining worktree changes are the five user-owned README/scripts/AWS identity paths explicitly excluded from this plan.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-22*
