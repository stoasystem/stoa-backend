---
phase: 473-student-content-privacy-and-practice-integrity
plan: 32
subsystem: conversation-content-deletion
tags: [dynamodb-transactions, account-fence, bedrock-leases, attachments, privacy, tdd]
requires:
  - phase: 473-22
    provides: atomic message attachment association and release lifecycle
  - phase: 473-23
    provides: exact attachment release and deletion reconciliation
  - phase: 473-29
    provides: permanent account fence and restartable deletion branches
provides:
  - closed conversation row, writer, private-field, tombstone, and provider-retention registries
  - permanent-fence transactions for conversation, command, quota, usage, attachment, lease, and completion writes
  - stale AI command invalidation and allowlisted private-row tombstones
  - restartable conversation_messages branch with association-first cleanup and two-clean-epoch proof
affects: [473-35, conversations, account-deletion, usage-ledger, attachments]
tech-stack:
  added: []
  patterns:
    - every private conversation mutation carries one exact permanent account-fence generation
    - stale provider returns lose to an atomic fenced completion transaction
    - attachment release precedes message/reference minimization and persists retry debt
key-files:
  created:
    - tests/test_phase473_conversation_deletion.py
  modified:
    - src/stoa/db/repositories/attachment_repo.py
    - src/stoa/db/repositories/usage_ledger_repo.py
    - src/stoa/services/usage_ledger_service.py
    - src/stoa/services/account_deletion_service.py
    - src/stoa/routers/conversations.py
key-decisions:
  - Conversation rows, messages, notes, commands, chat operations, usage metadata, and attachment associations form one owner/generation deletion family.
  - Initial-message, regular, and SSE sends share the same command implementation and permanent-fence checkpoints.
  - Bedrock request/response retention is explicitly outside backend deletion control; only backend durable copies are claimed scrubbed.
  - Conversation quiescence requires association release, inactive commands, zero debt, and two later clean strong base-table scans.
patterns-established:
  - Repository-owned conversation writes replace direct router table mutations.
  - Conversation tombstones retain only closed lifecycle and numeric accounting facts.
requirements-completed: [V9PRIV-01, V9PRIV-02]
duration: 10 min
completed: 2026-07-18
---

# Phase 473 Plan 32: Conversation, Message-Command, and In-Flight AI Deletion Closure Summary

Conversation text, teacher-help state, command replay JSON, chat metadata, and attachment references now converge behind the permanent account fence, with late AI returns discarded and deletion proven through restartable association-first strong scans.

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-17T23:37:45Z
- **Completed:** 2026-07-17T23:47:23Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Added closed source registries for seven private row families, eight writer classes, private fields, tombstone fields, active command states, and the explicit Bedrock retention boundary.
- Removed direct conversation router writes and routed create, initial-message, regular, SSE, teacher-help, usage, attachment, quota, lease, renewal, and assistant completion effects through owner/generation-aware repository operations.
- Added a strong paginated conversation-family scan, stale command cancellation, strict allowlisted tombstones, association-first cleanup, retry debt, and two later clean epochs before quiescence.
- Added eight lower-bound RED/GREEN contracts covering source inventory, exact fence generation, text-only transactions, static writer closure, malformed/late pagination, stale leases, attachment release order, and external-provider honesty.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing conversation-copy, in-flight completion, and association-release tests** - `965dc24` (test)
2. **Task 2: Fence all conversation/message/command/note writers and invalidate stale leases** - `0d4d79d` (feat)
3. **Task 3: Drain commands, release associations, and scrub every conversation family** - `82c5061` (feat)

Additional correctness commit:

- `ad937d4` (fix) removes a duplicate test-fixture key detected by the expanded Ruff gate.

## Files Created/Modified

- `tests/test_phase473_conversation_deletion.py` - RED/GREEN row/writer registry, fence, stale lease, raw-row scrub, association ordering, restart, and provider-boundary contracts.
- `src/stoa/db/repositories/attachment_repo.py` - Conversation registries, fenced write builders, command/message/lease/completion fences, strong discovery, stale cancellation, and tombstones.
- `src/stoa/db/repositories/usage_ledger_repo.py` - Optional permanent-fence transaction for private chat usage events.
- `src/stoa/services/usage_ledger_service.py` - Carries the exact account generation into conversation usage events.
- `src/stoa/services/account_deletion_service.py` - Restartable `conversation_messages` drain/release/scrub branch with debt and later-clean proof.
- `src/stoa/routers/conversations.py` - Repository-owned create/help writes, optional initial-message command reuse, and repeated pre-provider/post-provider fence checks.

## Decisions Made

- The permanent account-fence generation is stored on every future conversation message, command, and private usage row so stale workers cannot substitute current mutable profile state.
- Text-only message commits receive the same account ConditionCheck as attachment sends; an empty association list is not a fence bypass.
- AI lease claim, renewal, and assistant completion all require the command ownership/generation and the canonical active fence in the same transaction.
- Provider-retained Bedrock request/response data is not represented as backend-purged; backend deletion covers only the durable rows and references controlled by this service.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Preserved inherited lower-fake compatibility without weakening production fence transactions**

- **Found during:** Task 3 full conversation-suite verification
- **Issue:** One inherited lost-response fake exposed `get_item` but not a DynamoDB transaction interface, so the new pre-provider fence resolver treated it as a production table and rejected the test before its intended race.
- **Fix:** Limited the compatibility generation to non-Dynamo in-memory tables; real tables with `meta` or `transact_write_items` still require the permanent strongly read fence.
- **Files modified:** `src/stoa/routers/conversations.py`
- **Verification:** The full 65-test conversation/deletion/usage set and expanded 100-test attachment/retention set pass.
- **Committed in:** `82c5061`

**2. [Rule 1 - Bug] Removed duplicate fixture key found by expanded lint**

- **Found during:** Overall verification
- **Issue:** The command test fixture repeated `created_at`, which was behaviorally harmless but violated Ruff F601.
- **Fix:** Removed the duplicate literal while retaining the original timestamp field.
- **Files modified:** `tests/test_phase473_conversation_deletion.py`
- **Verification:** Targeted Ruff and all 100 focused tests pass.
- **Committed in:** `ad937d4`

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both corrections preserve the required test and production trust boundaries; no new dependency, table, provider, or external effect was introduced.

## Issues Encountered

- Git metadata is read-only in the normal workspace sandbox. Required atomic commits used the approved escalated Git path, with normal repository hooks enabled.

## Verification

- RED gate: eight intended assertion failures, pytest exit code exactly 1, with no collection/import failure.
- Task 2 GREEN gate: 18 selected writer/fence/regular/SSE/lease/completion/attachment tests passed.
- Final focused gate: 100 tests passed across conversation deletion, conversations, usage ledger, saved attachments, and retention reconciliation.
- Targeted Ruff passed across every Plan 32 source path and the new test; `git diff --check` passed.
- Static router scan reports no direct `.put_item(` or `.update_item(` mutation.
- TDD order is present in Git history: `965dc24` precedes `0d4d79d` and `82c5061`.

## Known Stubs

None.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| threat_flag: trust-boundary-schema | `src/stoa/db/repositories/attachment_repo.py` | New owner/generation tombstone and command fields cross the DynamoDB persistence boundary; the plan threat model explicitly covers this surface. |

## User Setup Required

None - no package, configuration, provider, or external-service change is required.

## Next Phase Readiness

- Plan 35 can consume the registered conversation branch evidence without allowing it to finalize the permanent account fence independently.
- Bedrock-side provider retention remains outside backend deletion control and must be evaluated under the milestone's external provider policy/evidence gate.
- No unresolved local blockers.

## Self-Check: PASSED

- All six created or modified delivery paths exist.
- Commits `965dc24`, `0d4d79d`, `82c5061`, and `ad937d4` exist in repository history.
- All mandatory Plan 473-32 local verification gates pass from committed source.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-18*
