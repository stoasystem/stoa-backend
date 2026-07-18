---
phase: 473-student-content-privacy-and-practice-integrity
plan: 35
subsystem: source-sealed-account-deletion
tags: [ast-inventory, dynamodb-transactions, privacy, retention-policy, tdd]
requires:
  - phase: 473-29
    provides: permanent deny-first account fence and five primary purge branches
  - phase: 473-30
    provides: authoritative moderation lineage and restartable content scrub
  - phase: 473-31
    provides: report row/object/email intent closure and legal-hold debt
  - phase: 473-32
    provides: conversation/message-command and in-flight AI deletion closure
  - phase: 473-33
    provides: five practice and adaptive-learning deletion branches
  - phase: 473-34
    provides: notification/device/realtime closure and external receipt policy facts
provides:
  - deterministic source-sealed inventory for every reviewed durable/provider mutation sink
  - checked retained-evidence policy for bounded noncontent usage, security, and log facts
  - exact 17-branch runtime registry bound into every new deletion command and branch result
  - current-generation two-zero-epoch validation and exact-once permanent terminal transaction
affects: [475-accounting, 478-core-journeys, 481-product-reality-gate, account-deletion]
tech-stack:
  added: []
  patterns:
    - immutable reviewed mutating-source digests remain separate from regenerable checked output
    - command, branch results, and permanent fence share one inventory digest and generation
    - accepted external receipts are minimized policy facts outside backend purge authority
key-files:
  created:
    - scripts/generate_phase473_private_store_inventory.py
    - docs/security/phase-473-private-store-inventory.json
    - docs/security/phase-473-retained-evidence-policy.json
    - tests/test_phase473_private_store_inventory.py
    - tests/test_phase473_account_deletion_seal.py
  modified:
    - src/stoa/db/repositories/account_deletion_repo.py
    - src/stoa/services/account_deletion_service.py
    - tests/test_phase473_account_deletion.py
key-decisions:
  - A checked JSON refresh cannot approve a mutation; every mutating source file is independently sealed by a reviewed source digest in the generator.
  - The runtime registry is exactly 17 ordered branch IDs with immutable handler, root, and subfamily contracts; legacy aggregate aliases cannot complete deletion.
  - Only a same-table conditional command-and-fence transition can mark deletion complete, and replay reads the same minimized terminal receipt without removing the permanent fence.
  - Provider accepted, delivered, and acceptance-unknown receipts remain explicitly outside backend purge authority, while pending provider work and legal retention always block completion.
patterns-established:
  - Static mutation discovery emits one source-relative AST-bound row with owner, fence, fields, cursor, debt, quiescence, purge, and no-resurrection proof.
  - Aggregate completion requires every branch result to match the command generation and inventory contract with zero cursor, zero blocking debt, and at least two authoritative zero epochs.
requirements-completed: [V9PRIV-01, V9PRIV-02, V9PRIV-03]
duration: 27 min
completed: 2026-07-18
---

# Phase 473 Plan 35: Source-Sealed Private-Store Registry and Account Deletion Finalizer Summary

A deterministic AST inventory now seals every reviewed private mutation to an exact 17-branch deletion proof, and one same-table CAS permanently terminalizes the command and account fence only after current-generation, two-epoch, zero-debt evidence.

## Performance

- **Duration:** 27 min
- **Started:** 2026-07-18T10:15:24Z
- **Completed:** 2026-07-18T10:42:30Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments

- Added stdlib AST discovery for direct and wrapped DynamoDB, S3/multipart, SES, SQS, Cognito, push HTTP, WebSocket, and private AI/provider mutations, with an independent reviewed-source digest barrier that synthetic writes cannot bypass by regenerating JSON.
- Generated a deterministic 19,000-line source-relative private-store inventory and a narrow retained-evidence policy covering only bounded noncontent usage/accounting, keyed security evidence, and category-only logs.
- Replaced the nominal legacy registry with exactly 17 active source-backed handlers, including `moderation` and `external_delivery_debt`, and bound every command/result to inventory hash, generation, handler version, required roots, and subfamilies.
- Added final seal validation for missing/extra/duplicate/stale branches, incomplete cursors, ordinary/provider debt, legal hold, dishonest external receipts, and one-zero-epoch evidence.
- Added one exact-once same-table conditional transaction that permanently sets the command to `complete` and the canonical fence to `deleted`, retains only replay/accounting/policy facts, and returns the same receipt after a lost response.

## Task Commits

Each task was committed atomically:

1. **Task 1: Create failing source-discovery, evidence-policy, registry, and terminal-seal tests** - `5011fc1` (test)
2. **Task 2: Generate deterministic private-store inventory and retained-evidence policy** - `08a9f78` (feat)
3. **Task 3: Seal deletion commands and finalize the permanent fence exactly once** - `81198ec` (feat)

## Files Created/Modified

- `scripts/generate_phase473_private_store_inventory.py` - AST sink discovery, reviewed-source seal, branch mapping, evidence validation, deterministic rendering, and semantic `--check`.
- `docs/security/phase-473-private-store-inventory.json` - Source-relative mutation rows, reviewed exclusions, selectors, and exact 17-branch runtime projection.
- `docs/security/phase-473-retained-evidence-policy.json` - Bounded field/basis/TTL/access policy for noncontent evidence and honest external receipt classification.
- `src/stoa/db/repositories/account_deletion_repo.py` - Terminal command/fence transaction, minimal receipt persistence, exact-once replay, and sealed branch-result fields.
- `src/stoa/services/account_deletion_service.py` - Runtime inventory loader, command binding, exact registry, external-delivery composition, seal validation, and finalizer orchestration.
- `tests/test_phase473_private_store_inventory.py` - Determinism, synthetic sink, exclusion, evidence-denial, and collected lower-selector tests.
- `tests/test_phase473_account_deletion_seal.py` - Exact branch mutation matrix, stale projection refusal, worker revalidation, CAS, and replay tests.
- `tests/test_phase473_account_deletion.py` - Command inventory binding and exact Plan 35 registry assertions.
- `tests/test_phase473_derived_content_purge.py` - Inherited moderation branch assertion updated to the sealed canonical ID.

## Decisions Made

- The checked inventory is evidence, not authority to approve a source mutation. Source approval lives in a separate reviewed digest map, so JSON regeneration alone cannot bless a newly inserted sink.
- `capability_repo` is always mapped to `capability_scope`; only teacher applications, privileged/admin identity, authored/public curriculum, and subscription billing/accounting receive reviewed non-student exclusions.
- Every branch contract is ordered and byte-hash-bound. A running command cannot migrate to a smaller/different registry or silently reuse stale handler/subfamily evidence.
- External accepted/delivered/unknown facts are nonblocking only when minimized and labeled outside backend purge authority. Pending work, ordinary debt, and legal-retention blockers remain terminal blockers.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated the inherited moderation aggregate-key assertion**

- **Found during:** Task 3 inherited branch verification
- **Issue:** Plan 30's test still asserted the provisional `moderation_support` aggregate alias, while Plan 35 requires the exact canonical branch ID `moderation`.
- **Fix:** Updated the inherited assertion while preserving the already-tested moderation handler implementation and purge behavior.
- **Files modified:** `tests/test_phase473_derived_content_purge.py`
- **Verification:** All 41 inherited deletion-branch tests and the 1,859-test full suite pass.
- **Committed in:** `81198ec`

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** The adjustment removes one superseded provisional registry name; no branch behavior, provider, schema table, or external effect changed.

## Issues Encountered

- The first AST pass recognized name-form transaction wrappers but not attribute-form repository wrappers. Attribute-form `transact` discovery was added before generation, preserving the reviewed-file digest barrier and producing a source-backed `moderation` row rather than weakening coverage.

## Verification

- RED gate: 38 intended assertion failures with pytest exit code exactly 1 and no collection/import error.
- Task 2 gate: deterministic generation twice, byte comparisons, semantic `--check`, 21 inventory/evidence/synthetic-mutation tests, and targeted Ruff all pass.
- Task 3 gate: inventory `--check`, seal/account/inventory suites, exact registry/finalizer matrix, and targeted Ruff all pass.
- Inherited branch gate: 41 tests pass across moderation, reports, conversations, practice/adaptive learning, and notification/device/realtime deletion.
- Full repository regression: 1,859 tests pass.
- TDD order is present in Git history: `5011fc1` precedes `08a9f78` and `81198ec`.
- `git diff --check`, deletion checks, and untracked-file checks pass.

## Known Stubs

None.

## Threat Flags

No unplanned threat surface was introduced. Source-to-inventory trust, aggregate finalization, retained evidence, and provider/legal classification are the explicit boundaries covered by T-473-35-01 through T-473-35-05.

## User Setup Required

None - no package, configuration, provider, or external-service change is required.

## Next Phase Readiness

- Local Phase 473 implementation now has an exact source-sealed account deletion terminal gate and all 1,859 repository tests are green.
- Plans 473-27 and 473-28 remain deliberately unexecuted as directed; their status is unchanged.
- External S3/provider behavior, deployed cleanup/IaC, and production/deployed log evidence remain outside this local plan and must not be inferred from these tests.
- No unresolved local blocker remains.

## Self-Check: PASSED

- All created and modified deliverable paths exist.
- Task commits `5011fc1`, `08a9f78`, and `81198ec` exist in repository history.
- All mandatory Plan 473-35 local verification gates pass from committed source.

---
*Phase: 473-student-content-privacy-and-practice-integrity*
*Completed: 2026-07-18*
