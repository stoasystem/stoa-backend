---
phase: 474-deterministic-verification-and-gated-delivery
plan: 23
subsystem: web-dependencies
tags: [npm, audit, vite, babel, dependency-policy, web]

requires:
  - phase: 474-01
    provides: release-blocking dependency policy contract and RED fixtures
  - phase: 474-05
    provides: authoritative machine-readable Web-root lock policy
provides:
  - advisory-free authoritative Web root lock with exact npm-ci installation
  - supported in-range remediation for all four measured Web advisories
  - zero-exception PASS from the shared backend dependency policy
affects: [474-web-gate, 474-release-verification, V9QUAL-03, V9QUAL-05]

tech-stack:
  added: []
  patterns: [machine-readable npm audit, supported in-range lock remediation, exact npm-ci lock verification]

key-files:
  created: []
  modified:
    - /Users/zhdeng/stoa-frontend/package-lock.json

key-decisions:
  - "All measured Web-root advisories were repaired with supported versions inside existing dependency ranges; no D-11 exception was created."
  - "The frontend manifest remains unchanged while the authoritative lock records the repaired dependency graph."

patterns-established:
  - "Web dependency remediation uses npm's machine JSON, the exact root lock, and the backend-owned policy rather than prose output or a mobile substitute."
  - "Dependency changes that affect build tooling must pass npm ci, ESLint, and the TypeScript/Vite production build before commit."

requirements-completed: [V9QUAL-03, V9QUAL-05]

duration: 6 min
completed: 2026-07-19
---

# Phase 474 Plan 23: Web Dependency Remediation Summary

**The authoritative Web root lock now installs exactly with zero npm advisories and passes the shared release-blocking dependency policy without exceptions.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-07-19T16:32:47Z
- **Completed:** 2026-07-19T16:38:17Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Reproduced the RED machine audit with two High, one Moderate, and one Low Web-root findings before changing the lock.
- Upgraded Vite `6.4.2` to `6.4.3`, `form-data` `4.0.5` to `4.0.6`, `js-yaml` `4.1.1` to `4.3.0`, and `@babel/core` `7.29.0` to `7.29.7` within their existing supported ranges.
- Produced a final npm audit with zero vulnerabilities and a shared-policy PASS with no accepted exceptions.
- Preserved `package.json` unchanged and verified the repaired `package-lock.json` by exact `npm ci`, ESLint, and a production TypeScript/Vite build.

## Task Commits

The task was committed atomically after its RED/GREEN verification cycle:

1. **Task 1 GREEN: repair Web root advisories** - `f0650ee` (fix, frontend repository)

The RED gate used the existing machine-readable npm audit and backend policy against the pre-change lock. No new test file was added because the plan's fixed implementation scope contains only the two frontend root package files and the existing policy already supplies the executable acceptance test.

## Files Created/Modified

- `/Users/zhdeng/stoa-frontend/package-lock.json` - Advisory-free, npm-ci-exact Web dependency graph with lock SHA-256 `2a7762935fa88be068efa1cd3230e87cbc1e8899e4857a791a563da6d5ba5c17`.
- `/Users/zhdeng/stoa-frontend/package.json` - Verified unchanged; its existing semver ranges support the repaired lock versions.

## Decisions Made

- Applied supported fixes for every measured advisory, including non-blocking development findings, because fixes existed and an exception was neither necessary nor permitted by D-11.
- Kept declared dependency ranges unchanged; the lock-only update records patched releases and their compatible transitive dependency closure.
- Used the implemented backend authority command `check-frontend`; the plan text used at execution time named the unavailable `check-web` command, and the stored plan was corrected after execution so future reruns use the shipped CLI.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used the shipped authoritative Web-policy subcommand**

- **Found during:** Task 1 RED verification
- **Issue:** The plan verification used at execution time named `check-web`, but `scripts/dependency_policy.py` exposes `check-backend` and `check-frontend`; the named command exits at argument parsing before evaluating evidence.
- **Fix:** Ran the existing source-backed `check-frontend` subcommand against the exact authoritative Web root lock and machine audit. No backend policy source was changed outside this plan's ownership.
- **Files modified:** None
- **Verification:** Final `check-frontend` returned `PASS`, zero blockers, zero accepted exceptions, and the exact repaired lock SHA-256.
- **Committed in:** Not applicable; invocation-only correction

---

**Total deviations:** 1 auto-fixed (1 blocking command-name mismatch)
**Impact on plan:** The correction used the already-implemented authoritative policy and did not broaden scope or weaken enforcement.

## Issues Encountered

- The sandbox blocked the localhost registry tunnel. The already-approved narrow npm commands were rerun outside the filesystem/network sandbox through `http://127.0.0.1:8766`; no alternate registry or unreviewed package was used.
- The production build emits the existing Vite advisory that one generated application chunk exceeds 500 kB. The build succeeds, and bundle splitting is outside this dependency-remediation plan.

## Known Stubs

None. The package manifest and lock contain no UI data placeholders or unwired runtime values introduced by this plan.

## User Setup Required

None - no external service configuration required.

## Verification

- RED audit: 4 vulnerabilities — 2 High, 1 Moderate, 1 Low; all reported `fixAvailable: true`.
- Exact install: `npm ci` installed the committed root lock and reported zero vulnerabilities.
- Final machine audit: 0 Critical, High, Moderate, Low, or Info findings.
- Shared policy: `check-frontend` returned `PASS`, zero blockers, zero accepted exceptions, and lock SHA-256 `2a7762935fa88be068efa1cd3230e87cbc1e8899e4857a791a563da6d5ba5c17`.
- Web regressions: `npm run lint` passed; `npm run build` passed with Vite `6.4.3` after transforming 2,660 modules.
- The Web root `package.json` was unchanged, the frontend task paths were clean after commit, and the backend was clean before summary/tracking work.
- The mobile skeleton was neither audited nor changed.
- Production infrastructure, deployment, smoke, and rollback remained exact `NOT RUN`.

## Next Phase Readiness

- The Web-root dependency segment is ready for the canonical cross-repository release gate and later browser/service verification plans.
- Plan 474-26 remains intentionally incomplete and has no summary; its skipped Linux ARM64 boot smoke is not represented as PASS.

## Self-Check: PASSED

- The declared frontend manifest, repaired lock, and Plan 474-23 summary exist.
- Frontend task commit `f0650ee` exists and modifies only the root `package-lock.json`; it contains no tracked deletions.
- Machine audit, shared dependency policy, exact install, lint, production build, stub scan, and threat-surface scan passed.
- No endpoint, authentication path, file-access boundary, schema, package exception, mobile artifact, or production operation was introduced.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-19*
