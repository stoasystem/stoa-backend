---
phase: 474-deterministic-verification-and-gated-delivery
plan: 05
subsystem: release-security
tags: [dependency-policy, pip-audit, npm-audit, uv-lock, d-11]

requires:
  - phase: 474-03
    provides: Frozen Python 3.12 dependency bootstrap and authoritative runtime export
provides:
  - Exact fail-closed backend and Web dependency advisory policy
  - Lock-bound expiring exception schema with advisory-alias and owner-approval evidence
  - Repaired supported backend advisories and one exact temporary ecdsa exception
affects: [474-release-gate, backend-verification, frontend-verification, delivery-policy]

tech-stack:
  added: []
  patterns: [machine-readable audit parsing, exact lock-bound exceptions, fail-closed advisory drift]

key-files:
  created:
    - schemas/release/dependency-exceptions-v1.schema.json
    - scripts/dependency_policy.py
    - evidence/phase-474/dependency-exceptions.json
  modified:
    - tests/test_dependency_policy.py
    - pyproject.toml
    - uv.lock
    - requirements.txt

key-decisions:
  - "Owner approved one exact D-11 exception for ecdsa 0.19.2 and PYSEC-2026-1325 through 2026-08-18, bound to both advisory aliases, the current backend lock, proven-unreachable ECDSA operations, and immediate removal or separately reviewed replacement."

patterns-established:
  - "Dependency exceptions bind ecosystem, package, primary advisory, canonical aliases, installed version, lock SHA-256, scope, severity, reachability evidence, owner approval, expiry, and removal target."
  - "Missing, expired, stale, duplicate, broadened, alias-drifted, or lock-drifted exception records fail with policy exit 2."

requirements-completed: [V9QUAL-04, V9QUAL-05]

duration: 30min
completed: 2026-07-19
---

# Phase 474 Plan 05: Exact Dependency Policy and Advisory Repair Summary

**Machine-readable backend/Web dependency gates now reject every unaccepted blocker, while supported backend advisories are repaired and the sole unfixed ecdsa finding is accepted only by an exact 30-day, lock-bound, source-supported D-11 record.**

## Performance

- **Duration:** 30 min
- **Started:** 2026-07-19T08:38:02Z
- **Completed:** 2026-07-19T09:07:52Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Implemented closed parsers for `pip-audit` and root-Web `npm audit` JSON, with exact lock/export coverage, severity/reachability policy, canonical results, and policy exit codes.
- Upgraded every measured backend package with an available supported fix while preserving byte-exact `uv export --locked` equality.
- Added one owner-approved exception for `ecdsa==0.19.2`, `PYSEC-2026-1325`, aliases `CVE-2024-23342` and `GHSA-wj6h-64fc-37mp`, and `uv.lock` SHA-256 `68efeb83c23ff4683cba1ff735130c365e8f9ec16dfb0eff5959a827536748fa`.
- Bound the exception to the tested production fact that token verification accepts only `RS256` through `RSAKey`; runtime source invokes no affected ECDSA signing, key-generation, or ECDH path.
- Proved the live policy passes only with the exact record and fails with exit `2` when the record is absent.

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Specify exact dependency policy** - `5e792c3` (test)
2. **Task 1 GREEN: Enforce exact dependency policy** - `80d7201` (feat)
3. **Task 2 RED: Specify measured advisory repairs** - `5930f92` (test)
4. **Task 2 GREEN: Repair supported runtime advisories** - `79a77d0` (fix)
5. **Task 2 owner decision: Accept exact temporary ecdsa exception** - `9b676d0` (fix)

## Files Created/Modified

- `schemas/release/dependency-exceptions-v1.schema.json` - Closed v1 exception schema including canonical advisory aliases and explicit approval evidence.
- `scripts/dependency_policy.py` - Backend and authoritative Web audit evaluator with exact exception matching and fail-closed CLI results.
- `evidence/phase-474/dependency-exceptions.json` - Sole approved ecdsa exception, expiring `2026-08-18T09:00:00Z`.
- `tests/test_dependency_policy.py` - Exact audit, exception, tamper, lock/export, reachability, and source-bound regression coverage.
- `pyproject.toml` - Supported fixed minimum versions for measured vulnerable runtime packages.
- `uv.lock` - Authoritative repaired Python resolution.
- `requirements.txt` - Frozen runtime export kept byte-identical to current locked export.

## Decisions Made

- The owner selected option 2: accept one exact temporary D-11 exception rather than replace the authentication/cryptography boundary in this plan or wait indefinitely for upstream.
- The exception expires on `2026-08-18T09:00:00Z` and must be removed immediately when an upstream fixed release exists; otherwise replacing `python-jose`/`ecdsa` requires a separately reviewed authentication-library and cryptographic-boundary change no later than expiry.
- Advisory aliases are part of the exception identity, so a primary/alias change cannot silently reuse the approval.
- Backend audit findings begin conservatively as production-reachable; an approved exact exception may bind reviewed `proven-unreachable` evidence without broadening package, advisory, aliases, version, lock, scope, or severity.

## Verification

- `22 passed` in `tests/test_dependency_policy.py`; Ruff passed for policy and tests.
- `72 passed` across dependency policy, token verification, and public identity lifecycle focused regressions.
- Full backend suite: `2116 passed`, with two pre-existing deprecation warnings.
- `uv lock --check` passed; fresh locked runtime export matched `requirements.txt` byte for byte.
- Live `pip-audit` reported exactly one known vulnerability in one package; the policy accepted only the committed ecdsa exception and returned `PASS`.
- Re-evaluating the same live audit with an empty ledger returned `FAIL`, preserved the exact blocker identity, and exited `2`.
- Production infrastructure, deploy, smoke, and rollback: exact `NOT RUN`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Bound advisory aliases and owner approval as machine fields**
- **Found during:** Task 2 owner exception decision
- **Issue:** The initial schema retained only the primary advisory identifier and owner name, so an alias-identity change or unrecorded approval provenance could not be checked precisely.
- **Fix:** Added canonical unique advisory aliases and explicit approval evidence to the closed schema, evaluator identity, accepted receipt, committed exception, and tamper tests.
- **Files modified:** `schemas/release/dependency-exceptions-v1.schema.json`, `scripts/dependency_policy.py`, `tests/test_dependency_policy.py`, `evidence/phase-474/dependency-exceptions.json`
- **Verification:** Exact live audit passes; missing or alias-drifted records fail; 22 focused tests and full suite pass.
- **Committed in:** `9b676d0`

---

**Total deviations:** 1 auto-fixed (1 missing critical).
**Impact on plan:** The addition narrows exception authority and supplies the exact approval/audit identity required by D-11; it adds no runtime or delivery capability.

## Issues Encountered

- System DNS could not resolve `pypi.org` even outside the sandbox. The live audit was completed with a process-local, temporary PyPI address override; no system DNS, hosts file, repository configuration, or production state was changed.
- `ecdsa 0.19.2` has no upstream fixed release. The owner resolved the release-blocking decision by approving the exact temporary record documented above.

## Known Stubs

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Dependency policy and measured backend advisory repair are ready for the canonical release gate.
- The sole temporary exception remains automatically release-blocking after expiry or on any advisory, alias, version, lock, scope, severity, or record drift.
- Production operations remain exact `NOT RUN` pending later explicit operational approval.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-19*

## Self-Check: PASSED

- All seven declared implementation/evidence files exist.
- Commits `5e792c3`, `80d7201`, `5930f92`, `79a77d0`, and `9b676d0` exist in repository history.
- Focused, lock/export, live policy, fail-closed, and full-suite verification claims were reproduced before closeout.
