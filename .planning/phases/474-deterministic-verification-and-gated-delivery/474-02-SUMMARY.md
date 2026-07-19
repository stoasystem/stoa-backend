---
phase: 474-deterministic-verification-and-gated-delivery
plan: 02
subsystem: release-verification
tags: [python, json-schema, sha256, fail-closed, cli]

requires:
  - phase: 474-01
    provides: execution-derived three-repository candidate identity and exact infra-root .DS_Store exception
provides:
  - one typed local/CI release-gate command authority
  - closed source-bound gate receipt schema with canonical SHA-256 identity
  - distinct PASS, policy rejection, execution failure, and exact NOT RUN outcomes
affects: [474-deterministic-gates, 474-ci, 474-provenance, 474-delivery]

tech-stack:
  added: []
  patterns: [typed gate registry, canonical compact JSON hashing, digest-only subprocess diagnostics]

key-files:
  created:
    - tests/test_release_gate.py
    - schemas/release/gate-receipt-v1.schema.json
    - scripts/release_gate.py
  modified: []

key-decisions:
  - "The CLI accepts only a closed gate ID; executable argv comes exclusively from a typed checked-in registration."
  - "Canonical receipt SHA-256 covers every stable field except the digest field itself."
  - "Policy rejection and exact NOT RUN return exit 2, unexpected execution failure returns exit 3, and only complete PASS returns exit 0."

patterns-established:
  - "Closed source binding: every receipt embeds the exact Plan 474-01 backend/frontend/infra identity and verifies its canonical execution digest."
  - "Privacy-safe execution: stdout and stderr are retained only as SHA-256 digests; environment and secret values are never serialized."

requirements-completed: [V9QUAL-01, V9QUAL-02, V9QUAL-03, V9QUAL-04, V9QUAL-05, V9QUAL-06]

duration: 12 min
completed: 2026-07-19
---

# Phase 474 Plan 02: Canonical Release Gate Contract Summary

**Typed release-gate orchestration with closed three-repository receipts, canonical SHA-256 identity, exact NOT RUN semantics, and redacted failure evidence.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-19T06:51:51Z
- **Completed:** 2026-07-19T07:03:31Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Defined a closed versioned receipt schema that binds the exact backend, frontend, and infra candidate identities from Plan 474-01.
- Added tamper tests for missing, duplicate, unknown, alternate-command, dirty-source, pass-shaped NOT RUN, privacy, and digest drift.
- Implemented a dependency-light Python CLI whose typed registry is the sole executable command graph for local and CI callers.
- Emitted deterministic receipts with canonical compact JSON hashing, exact input file identities, zero-tolerance PASS counts, and digest-only subprocess diagnostics.
- Preserved the owner-approved infra-root `.DS_Store` exception only through the authoritative Plan 474-01 candidate; no exception was generalized or reapplied here.
- Preserved production infrastructure, deploy, smoke, and rollback as exact `NOT RUN` source facts.

## Task Commits

Each TDD gate and implementation outcome was committed atomically:

1. **Task 1 RED: specify closed release gate receipts** - `b6902b7` (test)
2. **Task 1 GREEN: define closed gate receipt schema** - `886345d` (feat)
3. **Task 2 RED: specify authoritative gate orchestration** - `0c61425` (test)
4. **Task 2 GREEN: implement authoritative release gate** - `1d6241a` (feat)
5. **Task 2 acceptance: cover duplicate JSON rejection** - `4145620` (test)

## Files Created/Modified

- `tests/test_release_gate.py` - Closed schema, canonical hashing, typed registry, tamper, failure-class, privacy, and CLI contract tests.
- `schemas/release/gate-receipt-v1.schema.json` - Versioned closed receipt vocabulary for source, command, runtime, inputs, counts, privacy, and outcome classes.
- `scripts/release_gate.py` - Sole typed gate command surface with injectable Git, subprocess, clock, runtime, and platform operations.

## Decisions Made

- The CLI exposes `verify` and `self-test`, but accepts no caller-provided argv or shell command; CI can select only a checked-in registered gate ID.
- Receipt hashing excludes only `receipt_sha256`, preventing circular identity while binding every other stable field.
- A complete PASS requires at least one outcome, `passed == total`, and zero failed, error, skipped, xfail, or xpass counts.
- Exact `NOT RUN` is a zero-count obligation with a closed reason code and can never be shaped or counted as PASS.
- Unexpected execution exceptions are reduced to the stable `GATE_EXECUTION_ERROR` class with empty diagnostic digests; exception text is never serialized.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The managed filesystem initially denied Git index writes. The required normal verified commits were retried with repository write approval; no hook was bypassed and no Git state was reset, checked out, or stashed.

## Known Stubs

None. The initial registry intentionally contains the executable `gate-self-test`; later plans add reviewed capabilities through the same typed authority.

## User Setup Required

None - no external service configuration required.

## Verification

- `.venv/bin/python -m pytest -q tests/test_release_gate.py` — 25 passed.
- `.venv/bin/ruff check scripts/release_gate.py tests/test_release_gate.py` — all checks passed.
- Actual `self-test` CLI invocation produced `PASS`, exact zero-tolerance counts, Plan 474-01 candidate identity `0ce6ef7946e87ca41d05cb0c395ee58eea66dd61c41a100ede11ba06e9a3582c`, and a valid canonical receipt digest.
- `git diff --check` passed and the task worktree was clean after commits.

## Next Phase Readiness

- Plan 474-03 and later deterministic gate plans can add reviewed `GateSpec` registrations without creating a second local or CI command graph.
- No provider, sibling-repository, infrastructure, staging, or production mutation was performed.

## Self-Check: PASSED

- All three key files exist.
- Commits `b6902b7`, `886345d`, `0c61425`, `1d6241a`, and `4145620` exist.
- Both task verification commands and the plan-level verification commands pass.
- Stub and threat-surface scans found no goal-blocking placeholder and no unplanned trust boundary.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-19*
