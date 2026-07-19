---
phase: 474-deterministic-verification-and-gated-delivery
plan: 06
subsystem: release-provenance
tags: [python, json-schema, sha256, reproducible-builds, lambda, zip]

requires:
  - phase: 474-02
    provides: closed release-gate receipt vocabulary and typed gate IDs
provides:
  - closed three-repository release manifest with non-circular release identity
  - final digest binding source, locks, runtimes, receipts, artifacts, and configs
  - frozen-export-verified reproducible Python 3.12 arm64 Lambda ZIP
affects: [474-staging, 474-promotion, 474-rollback, 479-infrastructure]

tech-stack:
  added: []
  patterns: [canonical compact JSON hashing, closed identity inventories, normalized ZIP metadata]

key-files:
  created:
    - schemas/release/release-manifest-v1.schema.json
    - scripts/release_manifest.py
    - tests/test_release_manifest.py
  modified:
    - scripts/build_lambda_dist.py
    - tests/test_lambda_dist_build.py

key-decisions:
  - "Release ID hashes only execution-receipted repository, lock, and runtime identities; the final manifest digest separately binds gates, artifacts, configs, and exact production NOT RUN obligations."
  - "The gate inventory is ordered and closed to fifteen required PASS receipts with unique receipt and run identities."
  - "Known uv output-destination header variants are normalized, while every dependency payload byte must equal a fresh frozen export."
  - "Lambda archives use sorted paths, a fixed timestamp, regular-file mode 0644, no symlinks or bytecode caches, and a final SHA-256 identity."

patterns-established:
  - "Two-stage provenance: compute pre-build release identity, then bind immutable final bytes without circular hashing."
  - "Build-once artifact: verify lock export, source/distribution trees, handler inventory, isolated boot smoke, normalized archive, then publish only the recorded digest."

requirements-completed: [V9QUAL-06]

duration: 15 min
completed: 2026-07-19
---

# Phase 474 Plan 06: Cross-Repository Manifest and Reproducible Backend Artifact Summary

**Closed three-repository provenance plus a frozen-lock, Python 3.12 arm64 Lambda artifact whose repeated builds produce byte-identical ZIPs.**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-19T08:09:32Z
- **Completed:** 2026-07-19T08:25:23Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added a closed versioned manifest that accepts only exact backend, frontend, and infra commit/tree/lock identities from execution-receipted state.
- Derived a non-circular release ID from source/lock/runtime identity and a separate canonical manifest SHA-256 that binds gate receipts, artifacts, configs, and production `NOT RUN` facts.
- Rejected dirty repositories, branches, tags, `latest`, research-time identities, missing/duplicate/unknown gates, failed gates, unknown fields, and any unrehashed tamper.
- Extended the Lambda builder to compare the committed runtime dependency payload with a fresh `uv export --locked`, bind `uv.lock`, source and distribution trees, handlers, and boot smoke, and normalize final ZIP bytes.
- Proved complete repeated builds from the same source and lock create equal manifests, equal archive identities, and byte-identical ZIP files.

## Task Commits

Each TDD task was committed atomically:

1. **Task 1 RED: specify closed release manifest** - `3e42321` (test)
2. **Task 1 RED correction: canonical receipt fixtures** - `701a51c` (test)
3. **Task 1 GREEN: implement immutable release manifest** - `d64a2ed` (feat)
4. **Task 2 RED: specify reproducible Lambda artifact** - `fe9a0cb` (test)
5. **Task 2 GREEN: build reproducible Lambda artifact** - `3679398` (feat)

## Files Created/Modified

- `schemas/release/release-manifest-v1.schema.json` - Closed Draft 2020-12 schema for repository, runtime, gate, byte, config, and production identities.
- `scripts/release_manifest.py` - Deterministic manifest builder and fail-closed tamper validator.
- `tests/test_release_manifest.py` - Stable identity, mutable-ref, duplicate receipt, unknown gate, production overclaim, and single-axis tamper matrix.
- `scripts/build_lambda_dist.py` - Frozen export validation, distribution hashing, isolated handler imports, normalized ZIP creation, and archive revalidation.
- `tests/test_lambda_dist_build.py` - Lock/source/handler/platform/archive/boot drift and full repeated-build coverage.

## Decisions Made

- Artifact and config bytes do not affect the pre-build release ID, so immutable paths can be selected before build; they do affect the final manifest digest, so changed bytes create a distinct final manifest and cannot be promoted under the old digest.
- All fifteen release prerequisites must be present once, in canonical order, with unique receipt and run identities and exact `PASS`; unavailable or failed work cannot become a release manifest.
- Phase 474 still has no production mutation authority: infrastructure, deploy, smoke, and rollback are each required to remain exact `NOT RUN` in this manifest version.
- The builder accepts only the two exact headers emitted by the same reviewed `uv export` command with stdout versus `--output-file requirements.txt`; it compares all dependency payload bytes exactly and rejects every other header or payload difference.
- Boot smoke uses an isolated Python 3.12 process, strips AWS/proxy variables, disables metadata and bytecode writes, imports both exact handler modules, and records only a closed PASS fact.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected non-hex receipt fixtures in the RED tamper matrix**
- **Found during:** Task 1 RED review
- **Issue:** The first generated fixture sequence extended beyond hexadecimal characters and could have tested malformed inputs instead of stable canonical receipts.
- **Fix:** Generated every receipt as a distinct 64-character lowercase hexadecimal value and reran the RED gate.
- **Files modified:** `tests/test_release_manifest.py`
- **Verification:** All 19 manifest tests remained RED before implementation and passed after GREEN.
- **Committed in:** `701a51c`

**2. [Rule 3 - Blocking] Normalized only deterministic uv output-destination header drift**
- **Found during:** Task 2 real frozen-export verification
- **Issue:** The committed and fresh exports had byte-identical dependency payloads, but uv records stdout versus `--output-file requirements.txt` in the generated two-line header.
- **Fix:** Accepted only those two exact reviewed header forms while retaining byte-for-byte comparison of the entire dependency payload and rejecting unknown generation headers.
- **Files modified:** `scripts/build_lambda_dist.py`, `tests/test_lambda_dist_build.py`
- **Verification:** The live committed export check passed with 32,242 fresh bytes; altered dependency payload and unknown-header tests fail closed.
- **Committed in:** `3679398`

**3. [Rule 1 - Bug] Prevented boot-smoke bytecode from destabilizing ZIP bytes**
- **Found during:** Task 2 full repeated-build acceptance test
- **Issue:** Import smoke created path-dependent `.pyc` files inside each build directory, producing different archive bytes despite identical source and lock inputs.
- **Fix:** Set `PYTHONDONTWRITEBYTECODE=1` for boot smoke and excluded bytecode/cache paths from archive inputs.
- **Files modified:** `scripts/build_lambda_dist.py`, `tests/test_lambda_dist_build.py`
- **Verification:** Two complete builds now produce equal manifests, identities, and byte-identical ZIP files.
- **Committed in:** `3679398`

---

**Total deviations:** 3 auto-fixed (2 Rule 1 bugs, 1 Rule 3 blocker).
**Impact on plan:** All fixes tighten deterministic evidence and fail-closed behavior; no dependency, deployment, provider, or production scope was added.

## Issues Encountered

- The managed sandbox denied normal access to the existing uv cache and Git index. Read-only uv verification and required atomic commits were retried with the approved narrow permissions; no hook was bypassed and no Git state was reset, stashed, or cleaned.
- Context7 was unavailable both as an MCP surface and local `ctx7` CLI. The exact research-approved uv command and installed uv behavior were verified directly; no package was installed or substituted.

## Known Stubs

None. Empty lists/dicts found by the scan are local accumulators, and the `handler = None` text is an intentional stale-source negative fixture.

## User Setup Required

None - no external service configuration required.

## Verification

- `.venv/bin/python -m pytest -q tests/test_release_manifest.py` - 19 passed.
- `.venv/bin/python -m pytest -q tests/test_lambda_dist_build.py tests/test_release_manifest.py` - 33 passed.
- `.venv/bin/ruff check scripts/release_manifest.py scripts/build_lambda_dist.py tests/test_release_manifest.py tests/test_lambda_dist_build.py` - all checks passed.
- Real `uv export --format requirements-txt --no-dev --no-emit-project --locked` comparison passed: 32,242 fresh bytes, committed requirements SHA-256 `dbd16564e8c33ee08fb45aef9085c7ccbeff70cbded05739639a7be72a278137`, lock SHA-256 `c0068b2c743abc3b884749ce0dcc1ac1bbb3fec64a86b57ed7c13c551bcb0dd1`.
- Python byte-compilation and `git diff --check` passed.
- Production infrastructure, deployment, smoke, and rollback remained exact `NOT RUN`.

## Next Phase Readiness

- Later staging and promotion plans can consume one exact manifest digest and the backend ZIP identity without rebuilding either artifact.
- Frontend artifact generation, CDK release topology, staging exercise, protected approval, promotion, and compensation remain owned by their later Phase 474 plans.

## Self-Check: PASSED

- All five key files exist.
- Commits `3e42321`, `701a51c`, `d64a2ed`, `fe9a0cb`, and `3679398` exist.
- Both task verification commands, the plan-level commands, live frozen-export comparison, compile check, and repeated-build acceptance passed.
- Stub and threat-surface scans found no goal-blocking placeholder and no unplanned trust boundary.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-19*
