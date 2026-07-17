---
phase: 473-student-content-privacy-and-practice-integrity
plan: 29
subsystem: account-deletion-lifecycle
tags: [fastapi, dynamodb-transactions, cognito, resumable-jobs, privacy]
requires:
  - phase: 473-22
    provides: canonical retention fences and generation-checked attachment transactions
  - phase: 473-23
    provides: typed attachment purge progress and exact-version provider cleanup
provides:
  - permanent deny-first account fence and immutable verified-subject deletion command
  - fenced profile, identity, capability, question, session, upload, and teacher-escalation writers
  - five independently resumable primary deletion branches with strong cursors and two clean epochs
  - route background continuation plus scheduled recovery of lost deletion triggers
affects: [473-30, 473-31, 473-32, 473-33, 473-34, 473-35, 475-accounting]
tech-stack:
  added: []
  patterns:
    - one permanent USER account fence as the transactional write authority
    - verified-token deletion replay without Actor or business capability construction
    - bounded strong base-table scans with durable dirty-pass and quiescence state
key-files:
  created:
    - src/stoa/db/repositories/account_deletion_repo.py
    - src/stoa/services/account_deletion_service.py
    - src/stoa/jobs/account_deletion.py
    - src/stoa/jobs/teacher_escalation.py
    - tests/test_phase473_account_deletion.py
  modified:
    - src/stoa/security/identity.py
    - src/stoa/deps.py
    - src/stoa/db/repositories/question_repo.py
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/routers/auth.py
key-decisions:
  - The permanent account fence is the only account-write truth; pending deletion never restores Actor authority and Plan 35 alone may terminalize it.
  - Deletion replay resolves only an immutable issuer/subject command fingerprint and returns the same opaque receipt after identity rows are terminalized.
  - Primary branch readiness requires two full clean strong-scan epochs, while malformed, repeated, or partial progress remains retryable debt.
patterns-established:
  - Every account-owned mutation checks the exact active canonical fence generation in the same transaction and updates require row existence.
  - External provider and queue effects persist debt first and recheck the canonical generation immediately before effect.
requirements-completed: [V9PRIV-01, V9PRIV-02]
duration: 33 min
completed: 2026-07-17
---

# Phase 473 Plan 29: Canonical Deny-First Account Fence and Primary Content Purge Summary

A permanent account fence now denies authority at deletion acceptance, supports exact verified-subject receipt replay, and drives five cursor-safe primary purge branches plus lost-trigger recovery.

## Performance

- **Duration:** 33 min
- **Started:** 2026-07-17T20:45:16Z
- **Completed:** 2026-07-17T21:17:51Z
- **Tasks:** 3
- **Files modified:** 27

## Accomplishments

- Added `DELETE /auth/me`, which atomically transitions the canonical fence and commits an immutable command before returning an opaque receipt and scheduling continuation.
- Made identity resolution deny from the permanent fence before profile or grants, while exact issuer/subject retries locate only the committed deletion command and never construct an `Actor`.
- Fenced profile, identity, public-registration, capability, question, teacher-session, upload, attachment-association, and teacher-escalation mutations on the same active generation.
- Implemented account/profile, identity/provider, capability-scope, question/OCR/session, and attachment branches with bounded strong scans, validated cursors, durable debt, and two clean quiescence epochs.
- Added scheduled command discovery and lease claiming so route-trigger loss, process restart, and expired work can resume without an active user session.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing replay, fence, race, and continuation contracts** - `abaf4be` (test)
2. **Task 2: Implement permanent fence, replay-only command, and fenced writers** - `acea5ed` (feat)
3. **Task 3: Implement exhaustive primary branches and real continuation** - `5d4ff1b` (feat)

Additional correctness fix: `b57a1ed` (fix) discovers embedded parent child summaries during strong scans.

## Files Created/Modified

- `src/stoa/db/repositories/account_deletion_repo.py` - Canonical fence, immutable commands, strong discovery, branch persistence, tombstones, provider debt, and cross-account scrub operations.
- `src/stoa/services/account_deletion_service.py` - Exact 17-branch registry, five primary handlers, two-epoch progress, Cognito revocation, and sealed-finalizer guard.
- `src/stoa/jobs/account_deletion.py` - Bounded pending-command discovery, lease claiming, reconstruction, and background continuation.
- `src/stoa/jobs/teacher_escalation.py` - Opaque queue consumer with owner lookup and generation recheck.
- `src/stoa/deps.py` and `src/stoa/security/identity.py` - Verified-token replay dependency and deny-first canonical fence resolution.
- `src/stoa/db/repositories/{user_repo,identity_repo,public_identity_repo,capability_repo,question_repo,attachment_repo}.py` - Same-generation transactional writer checks and primary purge helpers.
- `src/stoa/services/{attachment_service,public_identity_service,notify_service}.py` - Provider ordering, fence rechecks, pending-fence cleanup, and opaque durable delivery.
- `src/stoa/routers/{auth,questions,students,teachers}.py` - Classified deletion route and centralized fenced mutation callsites.
- `tests/test_phase473_account_deletion.py` - Replay, fence, pagination, cursor, quiescence, tombstone, trigger, and queue contracts.
- `docs/security/route-authorization-inventory.json` - Regenerated checked route classification for DELETE `/auth/me`.

## Decisions Made

- The account fence remains permanently present; resource retention fences may complete independently, but the account fence cannot be finalized by Plan 29.
- The deletion route uses signed-token identity only to create or replay one exact command. Pending users receive no profile, grant, or general application authority.
- Strong base-table scans, rather than eventually consistent GSI results, establish deletion completeness. A filtered empty page is progress, not completion.
- Provider identity removal and teacher escalation use durable debt before external effects and repeat the account-generation check immediately before those effects.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated inherited test fakes and the checked route inventory**

- **Found during:** Task 2
- **Issue:** Existing identity and public-lifecycle fakes had no canonical fence facts, and adding DELETE `/auth/me` made the checked route inventory stale.
- **Fix:** Added explicit active fence fixtures and regenerated the inventory without weakening production checks.
- **Files modified:** `tests/test_auth_security.py`, `tests/test_identity_authorization.py`, `tests/test_public_identity_lifecycle.py`, `docs/security/route-authorization-inventory.json`
- **Verification:** The inherited identity, public lifecycle, auth lifecycle, and route inventory suites pass.
- **Committed in:** `acea5ed`

**2. [Rule 2 - Missing Critical] Bound account-level attachment cleanup to deletion-pending state**

- **Found during:** Task 3
- **Issue:** Plan 23's account cleanup helpers still required an active fence, which is impossible after deny-first deletion acceptance and would leave upload/provider debt undeletable.
- **Fix:** Required the exact `deletion_pending` generation for account cleanup, permitted cursor progress under that state, and prevented account-fence completion through the resource-fence helper.
- **Files modified:** `src/stoa/db/repositories/attachment_repo.py`, `src/stoa/services/attachment_service.py`
- **Verification:** Saved attachment and retention reconciliation suites pass within the 206-test final gate.
- **Committed in:** `5d4ff1b`

**3. [Rule 1 - Bug] Corrected cursor identity and embedded parent-summary discovery**

- **Found during:** Task 3 final audit
- **Issue:** A normal DynamoDB last-item continuation key could collide with the row deduplication set, and nested parent child summaries were scrub-capable but not discoverable.
- **Fix:** Separated row and cursor tracking, rejected only genuinely repeated cursors, and included nested child summary collections in owner discovery.
- **Files modified:** `src/stoa/db/repositories/account_deletion_repo.py`, `tests/test_phase473_account_deletion.py`
- **Verification:** Malformed/repeating cursor, late-page command, two-epoch, tombstone allowlist, and embedded parent-summary tests pass.
- **Committed in:** `5d4ff1b`, `b57a1ed`

---

**Total deviations:** 3 auto-fixed (1 blocking, 1 missing critical, 1 bug)
**Impact on plan:** All fixes close correctness or security gaps directly required by the planned deny-first lifecycle; no unrelated scope was added.

## Issues Encountered

- Git metadata is outside the normal workspace-write sandbox; task commits used the approved escalated Git path. Normal repository hooks ran for every commit.

## Verification

- RED gate: 12 intended assertion failures with pytest exit code exactly 1 before implementation.
- Task 2 gate: 221 tests passed before the primary worker completion.
- Final plan gate: 206 tests passed across deletion, attachment, retention, route inventory, auth lifecycle, identity, public identity, notifications, teacher dispatch, and teacher reply SLA suites.
- Ruff passed for every Python path listed by the plan.
- `git diff --check`, strong-read source inspection, deletion checks, and untracked-file checks passed.

## Known Stubs

None.

## User Setup Required

None - no new dependency or external configuration is required.

## Next Phase Readiness

- Plans 473-30 through 473-34 can add their independent branches to the source-declared 17-branch registry.
- Plan 473-35 remains the only phase allowed to seal the exact registry and transition the permanent account lifecycle to its terminal state.
- No unresolved blockers.

## Self-Check: PASSED

- All 27 created or modified deliverable paths exist.
- Task commits `abaf4be`, `acea5ed`, `5d4ff1b`, and `b57a1ed` exist in repository history.
- All mandatory plan-level verification gates passed.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-17*
