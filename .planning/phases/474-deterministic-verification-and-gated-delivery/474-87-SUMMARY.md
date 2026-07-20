---
phase: 474-deterministic-verification-and-gated-delivery
plan: 87
subsystem: fresh-web-release-verification
tags: [web, node20, npm-ci, release-gate, deterministic-build, fail-closed]

requires:
  - phase: 474-86
    provides: exact live three-repository candidate capture and isolated source materialization
provides:
  - exact fresh-install Web subordinate verifier bound to one stable source walk
  - closed canonical Web gate-run receipt with private atomic publication
  - fixed Node 20/npm execution and complete ordered five-step evidence
affects: [474-88, 474-89, 474-91, 474-93, 474-94, V9QUAL-01]

tech-stack:
  added: []
  patterns:
    - exact npm-ci-from-lock verification
    - closed subprocess environment
    - stable no-follow source capture
    - private atomic evidence publication

key-files:
  created:
    - /Users/zhdeng/stoa-frontend/scripts/verify-release.mjs
    - /Users/zhdeng/stoa-frontend/schemas/release/web-gate-run-v1.schema.json
    - /Users/zhdeng/stoa-frontend/tests/release/verify-release.test.mjs
  modified:
    - /Users/zhdeng/stoa-frontend/package.json

key-decisions:
  - "Invoke the active distribution's npm-cli.js through the exact Node 20 executable; do not trust npx, npm shebangs, PATH-provided runtimes, or project runtime shims."
  - "Run exactly locked install, lint, typecheck, build, and the six explicitly enumerated pre-Plan-87 Web release-contract files in fixed order."
  - "Capture package, lock, manifest, source, generated tree, and artifact identity from stable no-follow walks before publishing one canonical private receipt."
  - "Keep candidate registration, formal aggregation, CI wiring, source handoff, Playwright, canonical OpenAPI/dependency claims, mobile/native, and production delivery outside this subordinate verifier."

patterns-established:
  - "Every command runs with private npm user/global config, a fixed script shell, lifecycle wrappers denied, and ambient Node/npm/Vite/AWS/Git inputs closed."
  - "Evidence publication requires a private external output parent, exclusive mode-0600 temporary file, fsync, atomic rename, directory fsync, and final byte/type/link/mode revalidation."

requirements-completed: []
completed: 2026-07-20
---

# Phase 474 Plan 87: Fresh Web Verifier Summary

**The frontend now has one exact Node 20 verifier that starts without `node_modules` or `dist`, installs only from the committed lock, executes the complete reviewed Web sequence, and publishes one closed subordinate receipt.**

## Performance

- **Completed:** 2026-07-20
- **Duration:** Not separately recorded across the adversarial hardening cycle
- **Tasks:** 1 TDD task with seven follow-up fail-closed hardening cycles
- **Files modified:** 4 frontend files

## Accomplishments

- Added the exact ordered steps `frontend-locked-install`, `frontend-eslint`, `frontend-typecheck`, `frontend-build`, and `web-release-contracts`; the final step runs six explicitly enumerated release test files.
- Pinned Node 20 and the matching npm CLI, isolated npm configuration, fixed `/bin/sh`, denied lifecycle wrappers and local runtime shims, and removed ambient Node/npm/Vite/AWS/Git influence.
- Bracketed source and generated state before and after every step, including double initial and final publication captures, so lock/source/output changes cannot be accepted as one run.
- Added a closed receipt schema containing bounded identities, hashes, exact logical arguments, outcomes, and counts without serializing command output or environment values.
- Required a current-user private output directory and mode-0600 atomic receipt publication with canonical JSON and whole-receipt SHA-256 verification.

## Task Commits

The frontend TDD and hardening sequence is complete at exact commit `2c6e08ff8241bdbe22adb61f286a470ac060c3bf`:

1. `c7124e6` RED — define the fresh Web verifier contract; `51936ed` GREEN — add the fresh locked verifier.
2. `2ed72b1` RED / `d1381b6` GREEN — reject shared npm configuration paths and isolate both npm config files.
3. `b10d434` RED / `19c7f1d` GREEN — require and pin the npm script shell.
4. `56545d8` RED / `5675e56` GREEN — reject verifier lifecycle wrappers.
5. `91321ea` RED / `6e25be2` GREEN — reject and pin against project runtime shims.
6. `21210b1`, `fbe267e` RED / `2e97a76` GREEN — require stable source brackets and a private output parent, then close verifier state.
7. `d2b80ca` RED / `2c6e08f` GREEN — bracket and double-check final publication state.

## Verification

- Focused verifier policy: `18 passed`, `0 failed`.
- Complete Web release tests: `53 passed`, `0 failed`.
- Full frontend ESLint: passed.
- Exact fresh source materialization and verifier execution: passed all `5/5` ordered steps with `0` failures and `0` omitted steps.
- Runtime: Node `20.20.2`, npm `10.8.2`, `darwin-arm64`.
- Source tree SHA-256: `b04d705c0c563ba10327aa2c5fb72ae3853ac9660c8e0016ca731342574ea873`.
- Package-lock SHA-256: `2a7762935fa88be068efa1cd3230e87cbc1e8899e4857a791a563da6d5ba5c17`.
- Artifact tree SHA-256: `220b8adbdd4e702875c3fe12052b49971c2f2c7cabe7d8b9d572d7ff7d0301d4`.
- Receipt SHA-256: `5b1e54be903b60b019ee791a4c24999e1eee90cf3cafcaf753a015c55e56c315`; published mode was `0600` in the private external output directory.
- Independent final audit reproduced the exact commit and evidence checks and reported no remaining Plan 87 blocker.
- Production infrastructure: exact `NOT RUN`.
- Production deploy: exact `NOT RUN`.
- Production smoke: exact `NOT RUN`.
- Production rollback: exact `NOT RUN`.

## Deviations from Plan

- Adversarial review expanded the original implementation with separate npm config files, a fixed script shell, lifecycle-wrapper denial, project-shim denial, stable source/output brackets, and double final publication checks. These changes closed real ambient-input and torn-publication paths without broadening the plan's product scope.

## Remaining Work

- Plan 88 must register and independently validate this subordinate receipt against the exact three-repository candidate.
- The non-selectable formal aggregate, three thin CI callers, source handoff, and final local/CI-contract parity remain pending.
- This receipt does not claim Plan 24's canonical `frontend-contract`, OpenAPI adapter semantics, dependency verification, Playwright, mobile/native, CI, deployment, smoke, or rollback evidence.
- Plan 87 advances V9QUAL-01 but does not complete it; `requirements-completed` therefore remains empty.

## Self-Check: PASSED

- All four declared frontend files and all listed commits exist at the exact clean frontend `HEAD`.
- Focused, complete release-test, lint, exact fresh-run, receipt-permission, and digest evidence passed.
- No aggregate, CI, source-handoff, mobile/native, or production operation is represented as completed.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-20*
