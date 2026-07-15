---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 13
subsystem: authorization
tags: [fastapi, pydantic, route-inventory, openapi, fail-closed]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    provides: executable route authorization metadata, canonical subject binding, and durable audit wiring
provides:
  - Cycle-safe identifier discovery across the full FastAPI dependency and annotation graph
  - Exact command-local and self-only declarations for deliberate public/global identifier commands
  - Deterministic 219-operation JSON and OpenAPI authorization projections with mutation canaries
affects: [phase-474-testing, phase-478-clients, authorization-inventory, openapi]

tech-stack:
  added: []
  patterns: [recursive annotation projection, exact scoped identifier declaration, executable-spec compatibility]

key-files:
  created: []
  modified:
    - src/stoa/security/route_inventory.py
    - src/stoa/routers/auth.py
    - src/stoa/routers/teacher_applications.py
    - tests/test_route_authorization_inventory.py
    - docs/security/route-authorization-inventory.json

key-decisions:
  - "Public identifier commands must declare the exact observed canonical identifiers with command-local scope and a narrow reason."
  - "Safe-public identifiers are accepted only through compatible executable dependency specs; endpoint declarations cannot substitute."
  - "Authenticated-global identifier commands are limited to exact Actor-self user identifiers under self-only scope."

patterns-established:
  - "One cycle-safe recursive projection supplies runtime validation, checked JSON, and OpenAPI metadata."
  - "Executable capability metadata is retained in inventory specs so command-local capability routes remain distinguishable from broad public declarations."

requirements-completed: [V9ACCESS-02]

duration: 10 min
completed: 2026-07-15
---

# Phase 472 Plan 13: Recursive Dependency Identifier Inventory Summary

**Every registered dependency and nested Pydantic/Annotated/container request shape now contributes sensitive identifiers to one fail-closed, byte-stable runtime/JSON/OpenAPI authorization inventory.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-15T13:36:26Z
- **Completed:** 2026-07-15T13:46:37Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Traversed every FastAPI dependant path/query/body field and recursively unwrapped Annotated, unions, optionals, sequences, tuples, sets, mappings, and nested/cyclic Pydantic models.
- Closed all 11 independently observed real-route blind spots while retaining their executable authorization specs.
- Added exact non-overlapping rules for explicit-public command-local declarations, safe-public executable contracts, and authenticated-global Actor-self declarations.
- Declared only `parent_id` on registration and `application_id` on teacher candidacy submission; resource reads, invitation tokens, arbitrary dictionaries, and wildcard families remain undeclared.
- Regenerated 219 unique method/path rows and proved checked JSON, runtime inventory, and OpenAPI extensions remain identical and deterministic.

## Task Commits

Each task was committed atomically:

1. **Task 1: Recursive dependency and annotation identifier discovery** - `98a4f1a` (feat)
2. **Task 2: Mutation coverage and deterministic inventory regeneration** - `821f220` (test)

## Files Created/Modified

- `src/stoa/security/route_inventory.py` - Recursive field/dependency walker, scoped declarations, and compatible executable-spec validation.
- `src/stoa/routers/auth.py` - Exact command-local `parent_id` registration declaration.
- `src/stoa/routers/teacher_applications.py` - Exact command-local `application_id` candidacy declaration.
- `tests/test_route_authorization_inventory.py` - Positive/negative canaries for nested shapes and every public/global class, plus 11 real-route assertions.
- `docs/security/route-authorization-inventory.json` - Regenerated deterministic 219-operation projection.

## Decisions Made

- Identifier declarations compare exact aliases after recursive observation; missing, extra, duplicate, wildcard, generic-reason, or wrong-scope declarations fail closed.
- Safe-public declarations never override dependency metadata, while current capability metadata is retained in the executable inventory spec.
- Recursive model protection is path-local, preventing cycles without suppressing the same schema when it appears in multiple branches.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The existing disabled login-code policy docstring contains the word `placeholder`; it is an intentional pre-existing fail-closed product policy, not a new implementation stub and does not affect this plan.
- The managed environment's default uv cache is read-restricted, so verification used `UV_CACHE_DIR=/tmp/stoa-uv-cache`; no dependency or source behavior changed.

## User Setup Required

None - no external service configuration required.

## Verification

- Plan-level route inventory, notification, and admin authorization suite: **170 passed**.
- Extended auth, public identity, teacher onboarding, and terminology regression: **239 passed**.
- Task 1 nested/Annotated/container/public/global/real-route gate: **16 passed**.
- Inventory: **219 rows / 219 unique method-path operations**.
- Consecutive generator runs and `--check`: **byte-identical**, SHA-256 `0d5e6d193febd94f6a80c48b5002e813d05b6b7fe815f1cef1b34d2bfa86a139`.
- Ruff and `git diff --check`: **passed**.
- No AWS, network, sandbox, provider, or production mutation was performed.

## Known Stubs

- `src/stoa/routers/auth.py:761` - Pre-existing explicit rejection of placeholder login codes; intentionally fail-closed until a separately planned Cognito custom-auth flow exists.

## Next Phase Readiness

- Plan 472-15 can normalize public Cognito failures against the exact public route boundary.
- Plan 472-16 can use the corrected deterministic inventory as final Phase 472 evidence.
- Phase 474/475 ownership boundaries remain unchanged.

## Self-Check: PASSED

- All five modified artifacts exist.
- Both task commits are present in history.
- Every task acceptance gate and the plan-level verification command passed.
- Runtime, checked JSON, and OpenAPI share the same identifier/spec projection.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
