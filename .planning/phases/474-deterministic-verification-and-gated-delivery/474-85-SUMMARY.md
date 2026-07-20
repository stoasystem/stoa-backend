---
phase: 474-deterministic-verification-and-gated-delivery
plan: 85
subsystem: release-gate-portability
tags: [release-gate, portability, multi-repository, schema, dependency-policy, fail-closed]

requires:
  - phase: 474-02
    provides: canonical candidate and receipt foundation
provides:
  - execution-only backend/frontend/infra root mapping
  - logical repository and canonical relative-path command/input identities
  - exact repository marker and authoritative Web lock validation
  - host-path-free candidate and gate receipts
affects: [474-24, 474-29, 474-30, 474-31, 474-76, V9QUAL-01]

tech-stack:
  added: []
  patterns: [logical repository identity, execution-only roots, canonical POSIX-relative paths]

key-files:
  modified:
    - scripts/release_gate.py
    - scripts/dependency_policy.py
    - schemas/release/gate-receipt-v1.schema.json
    - evidence/phase-474/candidate-identity.json
    - tests/test_release_gate.py
    - tests/test_dependency_policy.py
    - tests/test_deterministic_gate.py

key-decisions:
  - "Absolute checkout roots are execution inputs only and never enter candidate or receipt canonical bytes."
  - "Each logical repository is identified by a distinct resolved root, its authoritative lock, and an exact project-name marker."
  - "Gate paths use one canonical POSIX-relative grammar shared by runtime validation and the receipt schema."

patterns-established:
  - "Cross-repository gate registrations name backend, frontend, or infra and bind a repository-relative cwd plus repository-relative inputs."
  - "The Web dependency policy accepts an explicit root only when package.json identifies stoa-frontend and the audited lock is exactly that root's package-lock.json."

requirements-completed: []

duration: 24 min
completed: 2026-07-20
---

# Phase 474 Plan 85: Portable Gate Roots Summary

**The canonical gate can now run against caller-supplied backend, Web, and infra checkouts without signing workstation paths or accepting a duplicate, mobile, or wrong-repository root.**

## Performance

- **Duration:** 24 min
- **Completed:** 2026-07-20T00:28:26Z
- **Tasks:** 1 TDD task plus independent boundary review
- **Files modified:** 8 implementation/contract files, 2 historical command references, and this summary

## Accomplishments

- Removed `/Users/zhdeng/...` roots from candidate identity, receipt schema, registered command identity, and dependency policy.
- Added execution-only `WorkspaceRoots`, logical repository binding, repository-relative cwd/input hashing, logical `{python}` command identity, and explicit CLI root arguments.
- Rejected symlink roots and inputs, duplicate resolved roots, path traversal, non-canonical POSIX paths, overlong paths, wrong project markers, and mobile Web substitution.
- Migrated the frontend dependency command to require `--repo-root` and repaired the pending Plan 23 and validation commands so they remain executable.
- Preserved the historical candidate as historical evidence; exact live HEAD/tree/lock/porcelain matching remains a separate fail-closed plan.

## Task Commits

1. **Plan definition** - `9235a5b` (docs)
2. **Task RED: define portable root behavior** - `d05e33a` (test)
3. **Task GREEN: implement logical repository roots** - `7dc75b3` (feat)
4. **Review follow-up: align path grammar and pending commands** - `968a2cc` (included with the concurrent Plan 82 documentation commit)

## Verification

- `132 passed` across release gate, deterministic matrix, dependency policy, manifest, and persisted Python evidence tests.
- Ruff passed for both gate scripts and all modified test modules.
- Real `self-test` CLI completed with all three explicit roots; its canonical receipt contained no `/Users/`, `/private/`, or `/tmp/` path.
- `git diff --check` passed.
- Independent review found no remaining blocker after distinct-root, project-marker, canonical-path, and stale-command repairs.
- Production infrastructure, deploy, smoke, rollback, and repository mutation remain exact `NOT RUN`.

## Deviations from Plan

- Independent review found that lock filenames alone could not distinguish backend from infra or a copied Web lock from mobile. The implementation was strengthened with pairwise-distinct roots and exact project-name markers.
- Runtime path validation and the JSON schema initially differed for backslashes, repeated separators, dot segments, and length. They now share one canonical POSIX-relative contract.
- Five reviewed follow-up files were committed with Plan 82 documentation because another agent committed after they had been staged. History was not rewritten; the combined commit is recorded above.

## Remaining Work

- A later atomic plan must reject historical or stale candidates by matching each supplied checkout's live HEAD, tree, committed lock blob/worktree digest, and complete porcelain state.
- The final Linux local/CI equivalence plan must exercise arbitrary non-sibling checkout roots through the full aggregate CLI, not only the current single-gate self-test.
- Plan 85 advances V9QUAL-01 but does not complete it; full registry coverage, aggregate execution, thin CI callers, and source handoffs remain required.

## Self-Check: PASSED

- All declared implementation and test files exist.
- RED and GREEN commits exist in order.
- The working tree was clean after the implementation/follow-up commits.
- No requirement, phase, deployment, or production operation was falsely marked complete.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
