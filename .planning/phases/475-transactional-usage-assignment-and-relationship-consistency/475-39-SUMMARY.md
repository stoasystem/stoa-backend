---
phase: 475-transactional-usage-assignment-and-relationship-consistency
plan: 39
subsystem: api
tags: [fastapi, mypy, questions, typing]
requires:
  - phase: 475-14
    provides: redacted question submission validation route
  - phase: 475-17
    provides: versioned question state CAS
  - phase: 475-20
    provides: closed question replay, effect, and terminal result contracts
provides:
  - exact FastAPI coroutine handler typing for the question submission route
  - unfiltered mypy-clean question router
affects: [475-42, 475-43, 475-44, 475-45]
tech-stack:
  added: []
  patterns:
    - APIRoute overrides use the framework's exact Coroutine response contract
key-files:
  created: []
  modified:
    - src/stoa/routers/questions.py
key-decisions:
  - "Match APIRoute.get_route_handler with Coroutine[Any, Any, Response] instead of the wider Awaitable return."
  - "Keep replay, provider-effect, question-state CAS, terminal compensation, and response behavior unchanged."
requirements-completed: [V9DATA-01, V9DATA-02]
duration: 3 min
completed: 2026-07-23
---

# Phase 475 Plan 39: Question Router Type Closure Summary

**The question submission route now matches FastAPI's exact coroutine handler contract, closing the final unfiltered router mypy diagnostic without changing transactional question behavior.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-07-23T08:53:09Z
- **Completed:** 2026-07-23T08:56:37Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Replaced the overly broad `Awaitable[Response]` route-handler annotation with FastAPI's exact `Coroutine[Any, Any, Response]` contract.
- Preserved all question admission, strict replay, durable effect receipt, state/version CAS, terminal proof, reconciliation, and compensation code paths unchanged.
- Passed exact-file unfiltered mypy and all 67 planned question convergence regressions.

## Task Commits

1. **Eliminate question router mypy diagnostics** - `067f45c` (fix)

## Files Created/Modified

- `src/stoa/routers/questions.py` - Exact coroutine return annotation for the custom question submission route.

## Decisions Made

- Use the framework's precise coroutine return contract instead of an `Awaitable` supertype, because method override covariance requires the subclass callable to return the same or narrower type.
- Limit the change to imports and the override annotation; no runtime branch or persistence behavior was changed.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The repository sandbox initially denied creation of `.git/index.lock`; the already authorized exact-file `git add` and normal-hook `git commit` were rerun outside the filesystem sandbox.
- `ruff format --check` reports inherited whole-file formatting drift in `questions.py`. Reformatting would have changed many unrelated business lines, so this type-only plan retained the minimal diff. The required Ruff lint gate passes.

## Verification

- `.venv/bin/mypy src/stoa/routers/questions.py` - PASS, no issues in one source file.
- `.venv/bin/python -m pytest -q tests/test_phase475_question_admission.py tests/test_phase475_question_replay.py tests/test_phase475_question_effect_recovery.py tests/test_phase475_question_state_cas.py tests/test_phase475_question_reconciliation.py` - PASS, 67 passed.
- `.venv/bin/ruff check src/stoa/routers/questions.py` - PASS.
- `git diff --check -- src/stoa/routers/questions.py` - PASS.
- Normal Git hooks ran during commit `067f45c`.

## User Setup Required

None - no dependency, credential, schema, provider, or environment change is required.

## Known Stubs

None. Existing optional values and empty runtime accumulators in the router are operational defaults, not placeholders, and this plan introduced no new stubs.

## Threat Model

- Strict replay ownership and result classifications remain unchanged.
- Provider-effect, terminal proof, state-CAS, reconciliation, and compensation branches remain unchanged.
- No endpoint, authentication path, persistence shape, dependency, provider call, or other trust boundary was added.

## Next Phase Readiness

- The question router is ready for phase-wide unfiltered mypy and aggregate verification.
- Remaining Phase 475 plans can consume the existing closed replay/effect/terminal contracts without router-local type exemptions.

## Self-Check: PASSED

- `src/stoa/routers/questions.py` exists.
- Task commit `067f45c` exists and contains only `src/stoa/routers/questions.py`.
- Exact mypy, all planned regression suites, Ruff lint, and diff integrity checks pass.
- None of the five user-owned parallel files were staged or committed.

---
*Phase: 475-transactional-usage-assignment-and-relationship-consistency*
*Completed: 2026-07-23*
