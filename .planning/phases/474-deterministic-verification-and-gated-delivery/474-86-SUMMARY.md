---
phase: 474-deterministic-verification-and-gated-delivery
plan: 86
subsystem: exact-live-release-candidates
tags: [release-gate, git, exact-source, isolation, fail-closed]

requires:
  - phase: 474-85
    provides: portable logical backend/frontend/infra roots
provides:
  - explicit live three-repository candidate issuance
  - mandatory live candidate revalidation before every registered gate
  - exact Git-plumbing candidate workspaces with isolated object/index context
  - source-external atomic candidate and receipt output policy
affects: [474-87, 474-88, 474-89, 474-90, 474-91, 474-92, V9QUAL-01]

tech-stack:
  added: []
  patterns:
    - raw HEAD/index/worktree projection
    - exact blob materialization
    - scrubbed no-network Git subprocesses
    - end-bracketed live-state capture

key-files:
  modified:
    - scripts/release_gate.py
    - tests/test_release_gate.py

key-decisions:
  - "A retained evidence file can never authorize execution; verify and self-test require an explicit candidate matching all three live roots."
  - "Gate commands and input hashes use only exact candidate commit trees materialized without archive/export filters."
  - "Clean capture is read-only: HEAD and stage-zero index projections must match, while raw bytes/types/modes are verified without status, diff, filters, or write-tree."
  - "All Git processes deny ambient routing/configuration, lazy fetch, protocols, credentials, hooks, fsmonitor, and host-dependent ignore/case behavior."

patterns-established:
  - "Public gate authority performs live validation, exact materialization, a second live validation, snapshot execution, and in-snapshot receipt validation."
  - "Allowed output paths are absolute, external to every source root, removed before work, and atomically replaced only on success."

requirements-completed: []

duration: 75 min
completed: 2026-07-20
---

# Phase 474 Plan 86: Exact Live Candidate Summary

**Every public registered-gate invocation is now bound to an explicit candidate that exactly matches the current clean backend, frontend, and infra commits and executes only from isolated exact-tree snapshots.**

## Performance

- **Duration:** 75 min
- **Completed:** 2026-07-20T01:46:54Z
- **Tasks:** 1 adversarial TDD task plus repeated independent boundary review
- **Files modified:** 2 implementation/test files, the strengthened plan contract, and this summary

## Accomplishments

- Added `candidate` issuance from live HEAD/tree, committed and worktree lock bytes, index flags, HEAD/index mode-OID-path projections, raw tracked bytes/types/executable modes, and exact untracked inventory.
- Required explicit `--candidate` for `verify`/`self-test` and removed the historical candidate fallback from execution.
- Added exact tree materialization through `ls-tree`, `cat-file --batch`, and a copied standalone object context; executable files and safe symlinks are preserved, while gitlinks, unsafe paths, `.git` paths/symlinks, unsupported modes, filters, `export-ignore`, and `export-subst` cannot alter execution.
- Revalidated all three live roots again after materialization and before any registered command.
- Removed capture dependence on filter-sensitive `status`/`diff` and mutating `write-tree`; raw reads use no-follow directory descriptors and nonblocking special-file rejection.
- Scrubbed ambient Git variables/configuration, bound exact worktrees, disabled hooks/fsmonitor/untracked cache/lazy fetch/transport/credentials, and fixed case, Unicode, attributes, and excludes behavior.
- Rejected stale/dirty/torn candidates, swapped roots, lock drift, nonstandard index flags, tracked infra `.DS_Store`, staged deletion of a HEAD-tracked `.DS_Store`, core.worktree routing, external index/object/worktree routing, symlink emulation, parent-symlink routing, clean-filter normalization, FIFO replacement, and stale output reuse.

## Task Commits

1. **Plan definition:** `1a68674` — plan exact live candidates
2. **Task RED:** `4b1f031` — define exact live candidate contract
3. **Task GREEN:** `c2a524e` — bind gates to exact live candidates

## Verification

- `63 passed` in the focused release-gate contract.
- `158 passed` across release gate, deterministic matrix, dependency policy, release manifest, and persisted Python-evidence suites.
- Ruff, targeted strict mypy, and `git diff --check` passed.
- Multiple independent reviews found and closed ambient Git routing, repository-local worktree/filter/symlink/excludes/case behavior, mutating inspection, partial-clone fetch, special-file blocking, `.DS_Store` staged deletion, and torn-snapshot gaps; two final reviewers reported no remaining blocker.
- A real three-root candidate attempt rejected with policy exit 2 and left no output because the infra checkout contains existing uncommitted Plan 26 work. This is the required fail-closed result; Plan 92 owns the final clean three-root PASS after all source commits.
- Production infrastructure, deploy, smoke, rollback, and source mutation remain exact `NOT RUN`.

## Deviations from Plan

- The original porcelain approach was replaced with a stronger read-only raw projection because repository-local symlink and clean-filter configuration could hide tracked changes or execute code during inspection.
- Exact materialization uses copied Git objects rather than `git archive`, so Git-dependent tests work in the snapshot without honoring export attributes.
- Independent review expanded the Git isolation boundary to cover lazy fetch, credential/transport helpers, global ignores, case folding, Unicode precomposition, special files, and end-bracketed concurrent changes.

## Remaining Work

- Plan 87 must implement the exact fresh-install Web subordinate verifier.
- Plan 88 must expose a non-selectable full aggregate registry/entry point.
- Plans 89-91 must replace backend, frontend, and infra workflows with thin verification-only callers.
- Plan 92 must prove local/CI equivalence and issue the final post-commit three-repository candidate.
- Plan 86 advances V9QUAL-01 but does not complete it; V9QUAL-02 remains closed by the source-bound Linux two-run evidence.

## Self-Check: PASSED

- All task commits and declared files exist.
- The backend implementation commit is clean and independently reviewed.
- No production or source mutation is represented as executed evidence.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
