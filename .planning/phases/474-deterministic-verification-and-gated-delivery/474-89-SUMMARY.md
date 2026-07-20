---
phase: 474-deterministic-verification-and-gated-delivery
plan: 89
subsystem: fixed-formal-release-aggregate
tags: [release-gate, python, web, candidate, atomic-publication, fail-closed]

requires:
  - phase: 474-86
    provides: exact live candidate issuance and isolated three-repository materialization
  - phase: 474-88
    provides: candidate-bound Python hermetic and fresh Web registered child gates
provides:
  - one non-selectable formal Python then Web verification graph
  - closed source-bound two-child aggregate receipt
  - private external mode-0600 atomic receipt publication
  - exact aggregate PASS, FAIL, and NOT RUN priority semantics
affects: [474-90, 474-91, 474-92, 474-93, 474-94, V9QUAL-01, V9QUAL-02]

tech-stack:
  added: []
  patterns:
    - fixed non-caller-selectable aggregate graph
    - sequential independently materialized child snapshots
    - canonical frozen child evidence retained after snapshot cleanup
    - private dirfd no-follow atomic evidence publication

key-files:
  modified:
    - scripts/release_gate.py
    - tests/test_formal_release_gate.py
  created:
    - schemas/release/formal-gate-run-v1.schema.json

key-decisions:
  - "Formal is not a GateRegistry entry and accepts no gate, skip, only, order, or argv selection; it always runs backend-python-hermetic followed by frontend-web-fresh."
  - "Each child owns a separate three-repository snapshot; its validated receipt is canonically frozen before that snapshot closes, and no two child snapshots coexist."
  - "Outer classification priority is execution failure, policy rejection, exact NOT RUN, then PASS; only two PASS children can produce aggregate PASS."
  - "Formal evidence can only be published into an existing current-user mode-0700 external directory as one mode-0600 single-link file after final outer and candidate revalidation."

requirements-completed: []
completed: 2026-07-20
---

# Phase 474 Plan 89: Fixed Formal Release Aggregate Summary

**Local and later CI callers now have one authoritative, non-selectable Python-plus-Web entry point whose complete evidence is bound to one exact three-repository candidate.**

## Accomplishments

- Added the required `formal` command with exactly one candidate, three explicit repository roots, and one private external output; duplicate and graph-selection arguments fail in parsing.
- Fixed the graph to `backend-python-hermetic` then `frontend-web-fresh`, retaining the second obligation after every valid first-child PASS, policy failure, execution failure, or exact NOT RUN.
- Kept child materializations strictly sequential. Each registered child completes semantic validation and canonical deep-copy freeze while its own snapshot is alive; the outer validator never pretends to recreate a deleted Web `dist` tree.
- Added a closed formal schema and semantic validator for exact source, command, runtime, input, child order, child and outer digests, two-obligation classification, privacy, time order, and four production `NOT RUN` values.
- Added final source-drift brackets and private publication through an existing mode-0700 owner directory, exclusive no-follow mode-0600 temporary file, file and parent fsync, same-directory atomic replace, final inode verification, and failure/stale cleanup.
- Protected authoritative and caller-supplied source roots before any stale-output unlink, including direct publisher use, and restricted outer/child/Web runtime identities to the exact supported platform mapping.

## Task Commits

1. `a620a6f` RED — define the fixed graph, classification matrix, closed schema shape, and private publication contract.
2. `58c6822` GREEN — implement the formal aggregate, semantic validator, schema, secure publisher, and adversarial regressions.

Planning commits `70b71cb` and `5068219` fixed the aggregate scope and strict non-overlapping child-snapshot lifetime before implementation.

## Verification

- Exact Plan suite: `187 passed`, `0 failed` across `tests/test_formal_release_gate.py`, `tests/test_release_gate.py`, and `tests/test_release_manifest.py`.
- Focused formal suite: `45 passed`, including graph substitution, all 16 result combinations, non-PASS continuation, snapshot freeze, source drift, outer/child tamper, time overlap, runtime/privacy, hostile output, hardlink, callback failure, stale invalidation, and source-preservation cases.
- Ruff: passed.
- `mypy --strict scripts/release_gate.py`: passed.
- JSON parsing and `git diff --check`: passed.
- Two independent read-only adversarial reviews: final PASS with no remaining blocker or major finding.
- Real Darwin ARM64 formal invocation from clean backend `58c6822e225f44b5221785934a0151d9dec5d83c`, frontend `2c6e08ff8241bdbe22adb61f286a470ac060c3bf`, and infra `37a2a9b9c40b38fcfa6f62f36f6347234f0a69f4`: both children and aggregate emitted exact `NOT RUN / NOT_RUN_OBLIGATION / EXTERNAL_CHECK_UNAVAILABLE`, proving unsupported isolation cannot become PASS.
- Real candidate identity: `a63c06ab4b93b6ceb28db9c12bb05226b9b191ef36c9126777f56ad847e0ccac`.
- Formal canonical receipt SHA-256: `43a2ec7f5536ca30711b76b2b193d3cda4d750ba92fee80c989056e0fccc66ac`; published file SHA-256: `0afc27be82994ed4bdd8bdf5d02e73761b9492bcc1974ed221a5f56ef5b3c709`; published mode: `0600`, links: `1`.
- Production infrastructure, deploy, smoke, and rollback: exact `NOT RUN`.

## Deviations from Plan

- Independent review found that alternate caller roots could otherwise misclassify an authoritative source file as an external stale target. Source-root protection was moved ahead of every unlink and then down into the publisher itself.
- The initial broad platform string shape could not substantiate the no-environment-value privacy claim. Outer, child, and Web runtime identities are now closed to four supported host mappings and must agree.
- No workflow, provider CI, staging, deployment, mobile/native, or production action was added or executed.

## Remaining Work

- Plans 90, 91, and 92 must make backend, frontend, and infra CI invoke only this exact formal entry point from exact SHA inputs.
- Plan 93 must commit and freeze the final cross-repository source handoff.
- Plan 94 must run the complete fixed formal graph twice in no-host-mount Linux from the exact final source and retain the V9QUAL-01/V9QUAL-02 evidence.
- Provider-hosted workflow execution remains exact `NOT RUN` until the source is pushed and a separate provider run is authorized; production remains exact `NOT RUN`.
- Plan 89 advances but does not alone complete V9QUAL-01 or V9QUAL-02; `requirements-completed` remains empty.

## Self-Check: PASSED

- All three declared implementation files and both task commits exist.
- The full contract suite, static checks, two independent audits, direct source-preservation defense, private publication, and real unsupported-host result were reproduced.
- No source repository, provider, staging, production, mobile, or native mutation occurred.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
