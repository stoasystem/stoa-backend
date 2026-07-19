---
phase: 474-deterministic-verification-and-gated-delivery
plan: 03
subsystem: release-verification
tags: [python, pytest, uv, hermetic, network-isolation, deterministic-time]

requires:
  - phase: 474-02
    provides: typed authoritative release gate and closed source-bound receipt contract
provides:
  - exact research-approved Python verification toolchain pinned in the frozen lock
  - strict pytest node accounting with fixed clock, seed, runtime, lock, and collection identity
  - two-fresh-environment Python 3.12 matrix with fail-closed OS network isolation
  - Python 3.12-compatible Phase 473 AST source seals that preserve reviewed canonical bytes
affects: [474-ci, 474-quality-gates, 474-provenance, phase-473-evidence]

tech-stack:
  added: [pip-audit, time-machine, pytest-socket, boto3-stubs, types-python-jose]
  patterns: [acquire-before-isolate, exact NOT RUN obligation, closed pytest outcomes, version-independent AST seals]

key-files:
  created:
    - scripts/phase474_pytest_guard.py
  modified:
    - pyproject.toml
    - uv.lock
    - tests/conftest.py
    - tests/test_deterministic_gate.py
    - scripts/release_gate.py
    - scripts/generate_phase473_private_store_inventory.py
    - scripts/generate_phase473_boundary_inventory.py
    - tests/test_phase473_private_store_inventory.py
    - tests/test_phase473_boundary_inventory.py

key-decisions:
  - "Dependency acquisition may use the approved package host before isolation, but formal pytest processes receive no proxy or AWS credential paths and must run behind a proved OS network-none boundary."
  - "A host without a proved Linux network namespace emits exact NOT RUN with zero run counts; it never falls back to plugin-only isolation or claims PASS."
  - "Phase 473 AST seals use a version-independent serializer that reproduces the already-reviewed Python 3.14 canonical bytes on Python 3.12; checked evidence is not regenerated."

patterns-established:
  - "Formal Python matrix: two absent, distinct UV_PROJECT_ENVIRONMENT paths, frozen Python 3.12 sync, identical suite argv, and collection equality across standard/future clocks."
  - "Strict pytest evidence: empty, fail, error, skip, xfail, and xpass all fail; manifests retain only node/outcome phases and deterministic identities."

requirements-completed: [V9QUAL-01, V9QUAL-02]

duration: 18 min
completed: 2026-07-19
---

# Phase 474 Plan 03: Fresh Hermetic Python Verification Summary

**Pinned Python 3.12 verification now runs through one two-environment, fixed-clock, credential-free, network-none matrix with strict zero-non-pass pytest evidence.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-19T07:46:33Z
- **Completed:** 2026-07-19T08:04:13Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments

- Pinned every research-approved verification dependency exactly, regenerated `uv.lock`, and proved the checked runtime `requirements.txt` remains byte-equivalent to the frozen production export.
- Added central fixed-time, AWS credential denial, socket denial, deterministic seed, and strict node-accounting integration without changing normal developer pytest behavior.
- Registered `backend-python-hermetic` in the authoritative release gate; it creates two fresh frozen Python 3.12 environments, runs identical suite argv at the standard and future clocks, and rejects source, lock, collection, runtime, or outcome drift.
- Proved direct Python network access is denied by `pytest-socket` and spawned-process access is denied by the required OS boundary; plugin-only isolation cannot produce release evidence.
- Preserved exact Phase 473 private-store and boundary inventory bytes under Python 3.12 by removing Python-version-dependent `ast.dump` defaults from their source seals.
- Reproduced the complete ordinary Python 3.12 suite with **2,065 passed**; the formal matrix correctly reports exact `NOT RUN` on this macOS host because no supported OS network-none boundary exists.
- Performed no infrastructure, provider, staging, production deploy, production smoke, or rollback operation.

## Task Commits

Each TDD gate and implementation outcome was committed atomically:

1. **Task 1 RED: specify deterministic Python gate** - `796ea6f` (test)
2. **Task 1 GREEN: lock hermetic Python verification** - `37f8849` (feat)
3. **Task 2 RED: specify fresh Python matrix** - `9063fa3` (test)
4. **Task 2 blocker fix: stabilize Phase 473 AST seals on Python 3.12** - `25f5187` (fix)
5. **Task 2 GREEN: run the frozen Python verification matrix** - `fbe4129` (feat)

## Files Created/Modified

- `pyproject.toml` - Exact approved verification pins.
- `uv.lock` - Frozen 91-package project resolution including the approved toolchain.
- `requirements.txt` - Verified unchanged and byte-equivalent to the current locked production-only export.
- `scripts/phase474_pytest_guard.py` - Closed pytest report classification, strict manifest construction, deterministic collection identity, and formal plugin hooks.
- `tests/conftest.py` - Formal-only time-machine, pytest-socket, and AWS isolation integration.
- `tests/test_deterministic_gate.py` - Guard, matrix, NOT RUN, clock, network, AWS, freshness, and drift coverage.
- `scripts/release_gate.py` - Registered two-environment matrix, OS-boundary detection, fresh sync orchestration, manifest validation, and outer receipt mapping.
- `scripts/generate_phase473_private_store_inventory.py` - Runtime-independent AST source seals preserving existing reviewed bytes.
- `scripts/generate_phase473_boundary_inventory.py` - Matching runtime-independent boundary source seals.
- `tests/test_phase473_private_store_inventory.py` and `tests/test_phase473_boundary_inventory.py` - Python 3.12 canonical-seal regression coverage.

## Decisions Made

- Dependency acquisition happens before the hermetic boundary and may use only the operator-provided package transport. The formal test process removes every proxy and ambient AWS path.
- Linux `bwrap` or `unshare` must pass an actual network-namespace probe before it can wrap pytest. macOS and incapable Linux hosts return exact `NOT RUN`; no weaker fallback is eligible.
- Both fresh runs use the same `python -m pytest -q` argv and differ only through closed clock/environment identity. Their collection SHA-256 must match.
- Pytest manifests contain no stdout, stderr, exception, credential, provider, or private payload content—only closed node phases, counts, and deterministic identities.
- Phase 473 evidence remains immutable. The Python 3.12 compatibility repair reproduces the existing Python 3.14 `show_empty=False` AST representation rather than regenerating reviewed inventories.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Made Phase 473 source seals independent of the Python AST dump default**
- **Found during:** Task 2 complete-suite Python 3.12 verification
- **Issue:** Python 3.12 includes empty optional AST fields in `ast.dump`, while the reviewed Phase 473 inventories were sealed on Python 3.14 where those fields are omitted. Identical source therefore produced different digests and failed the fresh 3.12 suite.
- **Fix:** Added a narrow stable AST serializer to both Phase 473 generators that exactly reproduces the existing reviewed canonical bytes, including literal `None`, without regenerating evidence or changing semantic guards.
- **Files modified:** `scripts/generate_phase473_private_store_inventory.py`, `scripts/generate_phase473_boundary_inventory.py`, `tests/test_phase473_private_store_inventory.py`, `tests/test_phase473_boundary_inventory.py`
- **Verification:** Both generators pass `--check`; their outputs remain byte-identical to the checked inventories; the complete Python 3.12 suite reports 2,065 passed.
- **Committed in:** `25f5187`

---

**Total deviations:** 1 auto-fixed blocking issue.
**Impact on plan:** The repair was required to make the mandated Python 3.12 runtime deterministic and preserved every existing Phase 473 evidence byte and semantic boundary.

## Issues Encountered

- Initial package resolution was blocked by host DNS. The user-approved localhost CONNECT tunnel restricted to `pypi.org` and `files.pythonhosted.org` restored acquisition; all exact research-approved pins then resolved and synced successfully.
- This macOS host has no supported OS network-none boundary. The authoritative matrix and outer gate receipt therefore return exact `NOT RUN`/`NOT_RUN_OBLIGATION` with zero run counts, as required; this is not counted as PASS.

## Known Stubs

None.

## User Setup Required

None. CI must provide a proved Linux `bwrap` or `unshare` network namespace for formal PASS evidence; local macOS correctly remains `NOT RUN`.

## Verification

- `uv lock --check` — passed with 91 resolved packages.
- `.venv/bin/python -m pytest -q tests/test_deterministic_gate.py` — 24 passed.
- `.venv/bin/python -m pytest -q tests/test_deterministic_gate.py tests/test_release_gate.py` — 49 passed.
- `.venv/bin/ruff check scripts/release_gate.py scripts/phase474_pytest_guard.py tests/conftest.py tests/test_deterministic_gate.py` — passed.
- `generate_phase473_private_store_inventory.py --check` and `generate_phase473_boundary_inventory.py --check` — passed without evidence regeneration.
- Fresh locked production export compared byte-for-byte with `requirements.txt` — passed.
- Complete ordinary Python 3.12 suite — 2,065 passed, one third-party deprecation warning, in 70.11 seconds.
- Registered `backend-python-hermetic` gate — exact `NOT RUN`, `NOT_RUN_OBLIGATION`, `EXTERNAL_CHECK_UNAVAILABLE`, exit 2, and zero run counts on macOS.
- Production infrastructure, deploy, smoke, and rollback — exact `NOT RUN`.

## Next Phase Readiness

- Linux CI can now acquire from the frozen lock and produce two source-bound formal manifests behind a proved OS network-none boundary.
- Later Phase 474 plans can add Ruff, mypy, dependency, Web, artifact, and delivery obligations through the same checked-in gate registry.
- No provider or production mutation authority was introduced or exercised.

## Self-Check: PASSED

- All eleven planned and deviation key files exist; `requirements.txt` remains tracked and byte-equivalent to the locked runtime export.
- RED/GREEN and compatibility commits `796ea6f`, `37f8849`, `9063fa3`, `25f5187`, and `fbe4129` exist in Git history in the required order.
- Task checks, generator byte checks, lock/export verification, Ruff, focused tests, ordinary full Python 3.12 suite, and exact local NOT RUN behavior all reproduced after implementation.
- Stub and threat-surface scans found no goal-blocking placeholder and no unplanned endpoint, authorization, provider, schema, or production-operation surface.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-19*
