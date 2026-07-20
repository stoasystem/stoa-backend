---
phase: 474-deterministic-verification-and-gated-delivery
plan: 88
subsystem: candidate-bound-web-gate-registration
tags: [web, release-gate, candidate, node20, pid-namespace, fail-closed]

requires:
  - phase: 474-86
    provides: exact live candidate issuance and isolated three-repository materialization
  - phase: 474-87
    provides: exact fresh-install Web subordinate verifier and closed inner receipt
provides:
  - candidate-bound frontend-web-fresh registered gate
  - fixed official Node 20.20.2/npm 10.8.2 private toolchain resolution
  - Linux PID-namespace containment with exact unsupported-host NOT RUN
  - closed bidirectional gate, command, result, and evidence schema contracts
affects: [474-89, 474-90, 474-91, 474-92, 474-93, 474-94, V9QUAL-01]

tech-stack:
  added: []
  patterns:
    - official archive digest pinning before executable use
    - candidate source pre-seal and post-run three-way validation
    - PID-namespace descendant containment
    - exact unsupported-obligation classification

key-files:
  modified:
    - scripts/release_gate.py
    - schemas/release/gate-receipt-v1.schema.json
    - tests/test_release_gate.py

key-decisions:
  - "Never execute an ambient PATH/STOA_NODE binary; download one fixed official Node archive, verify its platform SHA-256, safely extract only Node plus the complete npm distribution, and re-seal that toolchain after the Web run."
  - "Seal package.json, package-lock.json, and the reviewed Plan 87 source tree before candidate code runs; require the inner receipt, pre-run seal, and two post-run captures to agree."
  - "A process group is not complete containment because setsid can escape it; Linux PASS therefore requires a trusted probed user/PID namespace, while unsupported hosts emit exact NOT RUN before Node download or candidate execution."
  - "Bind gate ID, command, result, and evidence in both schema and semantic validation so Web/Python evidence cannot be relabeled or paired with impossible failure reasons."

requirements-completed: []
completed: 2026-07-20
---

# Phase 474 Plan 88: Candidate-Bound Web Evidence Summary

**The backend authority now runs the exact Plan 87 Web verifier only from an isolated candidate snapshot, validates its complete evidence independently, and cannot issue Web PASS without a proved Linux descendant-containment boundary.**

## Accomplishments

- Registered the single internal `frontend-web-fresh` obligation with a backend-owned unpredictable private inner-receipt path and a closed launch environment.
- Removed all ambient Node resolution. The gate pins the official Node `20.20.2` archive and SHA-256 for four supported platform/architecture pairs, rejects proxy/redirect/oversize or unsafe archive input, and validates Node `20.20.2` plus npm `10.8.2` before and after execution.
- Bound the live candidate lock to a pre-run package/source seal before any candidate code starts, then required the inner receipt and two independent post-run captures to match it exactly.
- Added strict canonical/no-follow evidence reads, private cleanup, process-group defense in depth, and a trusted Linux `unshare` user/PID namespace that removes `setsid` and double-fork descendants on normal exit and timeout.
- Added exact `NOT RUN / NOT_RUN_OBLIGATION / EXTERNAL_CHECK_UNAVAILABLE` behavior with zero outcomes and null evidence when the containment boundary is unavailable.
- Closed schema and Python validation across the implemented self-test, Python hermetic, and Web gates, including reverse evidence binding and exact classification/reason tuples.

## Task Commits

1. `0f651ff` RED / `f21c471` GREEN — define and register candidate-bound Web evidence.
2. `5375e2c` RED / `c3d8324` GREEN — remove ambient Node trust and seal Web source before execution.
3. `bc43541` RED / `426adc5` GREEN — contain detached descendants, close schema cross-bindings, and require exact result tuples.

## Verification

- Exact Plan suite: `142 passed`, `0 failed` across `tests/test_release_gate.py` and `tests/test_release_manifest.py`.
- Ruff: passed.
- `mypy --strict scripts/release_gate.py`: passed.
- JSON parsing and `git diff --check`: passed.
- Independent final audit: PASS with no blocker, major, or minor finding.
- Unsupported Darwin execution: exact Web `NOT RUN`, zero outcomes, null evidence, receipt SHA-256 `3cc30fb91f81eda0cc26464524a883084d739205ca7921c8787eb8ddc701f794`.
- No-host-mount Ubuntu ARM64 execution from three detached Git-bundle checkouts: host and VM candidate JSON were byte-identical at candidate identity `ea2cbc140e12245e45c547ec93ffe9007013dae783b3636fe11a82465323aaa5`.
- Linux Web result: `5/5 PASS`, Node `20.20.2`, npm `10.8.2`, 26 artifact files, 3,432,822 bytes, artifact tree SHA-256 `220b8adbdd4e702875c3fe12052b49971c2f2c7cabe7d8b9d572d7ff7d0301d4`.
- Linux inner receipt SHA-256: `d8214c3edeaa167cf57cb14b9d086989aa70e816028f9066fd9762bd8da3e954`; outer file SHA-256: `66e8f7175af0bac335378035cc10690758989747c2dba995cb149df1a483293f`.
- Production infrastructure, deploy, smoke, and rollback: exact `NOT RUN`.

## Deviations from Plan

- Independent review found three additional trust-boundary defects after the first real Web PASS: an ambient executable path, a pre-run source-seal gap, and later a detached-process/schema tuple gap. Three explicit RED/GREEN cycles closed each defect before completion.
- Candidate-bound Web PASS is now intentionally Linux-only unless another platform can prove equivalent whole-descendant containment. This narrows claims without changing the Web product scope.

## Remaining Work

- Plan 89 must add the non-selectable formal aggregate over `backend-python-hermetic` and `frontend-web-fresh`.
- Separate atomic plans must replace backend, frontend, and infra workflows with the same exact formal caller, then freeze final source handoff and run the final Linux Python two-environment matrix.
- Plan 88 advances but does not alone complete V9QUAL-01; `requirements-completed` remains empty.
- Playwright, canonical OpenAPI/dependency gates, staging, production delivery, mobile/native, and provider CI execution are not claimed here.

## Self-Check: PASSED

- All three declared files and every listed commit exist at clean backend `HEAD` `426adc55e4ca9634c786de148e88894495b86cba`.
- Focused/full contract tests, static checks, independent audit, exact unsupported-host receipt, candidate byte equality, and real Linux ARM64 Web PASS were reproduced.
- No live repository, production infrastructure, deployment, smoke, or rollback mutation occurred.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
