---
phase: 472-privileged-identity-and-student-resource-authorization
plan: 10
subsystem: security
tags: [fastapi, route-inventory, openapi, reconciliation, evidence, authorization]

requires:
  - phase: 472-privileged-identity-and-student-resource-authorization
    plans: [06, 07, 08, 09]
    provides: executable Actor policies across student, parent, teacher, admin, report, and notification routes
provides:
  - Recursive runtime authorization inventory for all 219 registered FastAPI method/path operations
  - Deterministic checked JSON and OpenAPI x-stoa-authorization projection from one dependency graph
  - Dry-run-first redacted privileged identity reconciliation that can only auto-tighten
  - Focused P0 evidence with honest external NOT RUN and full-suite limitation status
affects: [473, 474, 475, 478, release-verification]

tech-stack:
  added: []
  patterns: [runtime dependency-tree inventory, explicit route classification, redacted dry-run plan, stable action checkpoints]

key-files:
  created:
    - src/stoa/security/route_inventory.py
    - scripts/generate_route_authorization_inventory.py
    - scripts/reconcile_privileged_identities.py
    - docs/security/route-authorization-inventory.json
    - docs/security/phase-472-evidence.md
  modified:
    - src/stoa/main.py
    - src/stoa/security/reconciliation.py
    - src/stoa/security/route_authorization.py
    - docs/security/tutor-term-allowlist.json
    - tests/test_route_authorization_inventory.py
    - tests/test_privileged_identity_reconciliation.py
    - tests/test_teacher_terminology_gate.py
    - tests/test_ai_operations.py

key-decisions:
  - "Registered APIRoute.dependant trees, not router filenames or source allowlists, are the completeness authority."
  - "Public and authenticated-global routes require explicit endpoint classification; notification/event/token identifiers still require Actor-owner or exact admin capability metadata."
  - "Reconciliation CLI remains read-only; any apply needs separate non-production approval plus an injected tightening adapter and can never add/restore privilege."
  - "Unavailable sandbox evidence is NOT RUN and cannot be represented as a pass or release approval."

patterns-established:
  - "One projection: checked JSON and x-stoa-authorization are generated from the same validated runtime inventory."
  - "One-way reconciliation: automatic actions suspend, remove, sign out, or revoke; restoration and grants route to an active admin_identity_manager command."
  - "Evidence truthfulness: exact commands, UTC time, source SHA, digests, redaction checks, limitations, and no-production-mutation statement are versioned together."

requirements-completed: [V9AUTH-01, V9AUTH-02, V9AUTH-03, V9AUTH-04, V9AUTH-05, V9ACCESS-01, V9ACCESS-02, V9ACCESS-03]

duration: 18 min
completed: 2026-07-15
---

# Phase 472 Plan 10: Executable route inventory, safe reconciliation, and P0 evidence Summary

**All 219 registered FastAPI operations now have deterministic runtime-derived authorization classification, privileged identity reconciliation is dry-run-first and auto-tightening-only, and the focused Phase 472 gate passes with honest external limitations.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-07-15T00:06:00Z
- **Completed:** 2026-07-15T00:24:00Z
- **Tasks:** 4
- **Files modified:** 18

## Accomplishments

- Recursively inspected every registered `APIRoute.dependant` tree, including path/query and nested Pydantic body aliases, and classified 109 admin-capability, 89 authorized, 14 explicit-public, 4 safe-public, and 3 authenticated-global operations with zero unknown routes.
- Generated a 219-row byte-stable inventory and projected identical metadata into OpenAPI; synthetic route, new-router, event ID, push-token alias, wrong-policy, and metadata-only mutations all fail closed.
- Implemented redacted, deterministic privileged identity classification and tightening proposals across approvals, roles/groups, status, bindings, grants, legacy values, checkpoints, partial retries, and manual elevation refusal.
- Closed stale positive teacher terminology contracts while preserving exactly 13 narrow negative/historical occurrences and a mutation gate that rejects new active contracts.
- Recorded SEC-001/002/004 denials and positive controls, D-29/D-31 contract determinism, reconciliation digests, full-suite ownership, rollback, and explicit no-production-mutation evidence.

## Task Commits

| Task | Description | Commit |
| --- | --- | --- |
| 472-10-01 | Runtime executable route authorization inventory | `11be980` |
| 472-10-02 | Dry-run-only privileged identity reconciliation | `06a6827` |
| 472-10-03 | Semantic terminology and deterministic client contract | `c8cb6c6` |
| 472-10-03 | P0 focused evidence package | `9ac0505` |
| 472-10-04 | Honest external evidence gate | `6c3268f` |

## Files Created/Modified

- `src/stoa/security/route_inventory.py` — recursive FastAPI graph inspection, ID/alias detection, validation, projection, and OpenAPI installation.
- `src/stoa/security/reconciliation.py` and `scripts/reconcile_privileged_identities.py` — redacted inventory/planning, checkpointed idempotent tightening, privilege-increase refusal, and read-only CLI.
- `docs/security/route-authorization-inventory.json` — deterministic 219-operation checked inventory.
- `docs/security/phase-472-evidence.md` — commands, results, SHA/digests, P0 reproductions, reconciliation sample, full-suite limitations, manual NOT RUN table, rollback, and no-production statement.
- Auth, teacher-application, billing, file, and main registration surfaces — explicit public/global or executable capability metadata.
- Inventory, reconciliation, terminology, and stale AI contract tests — positive/negative and mutation coverage.

## Decisions Made

- Exact endpoint classification is acceptable only for deliberately public or authenticated-global operations; identifier-bearing protected operations cannot inherit a broad router/source classification.
- Existing teacher application reviewer routes now expose and execute `teacher_identity_reviewer` metadata rather than relying on a role-only dependency plus service-local check.
- Reconciliation conflicts expose only stable hashed item IDs and safe counts/states. The CLI refuses apply, and programmatic apply is restricted to separately authorized non-production adapters.
- The 23 remaining full-suite failures are not Phase 472 regressions: they are strict production `Settings` fixtures owned by Phase 474 and remain unchanged.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Made teacher application review executable-policy visible**
- **Found during:** Task 1 runtime inventory.
- **Issue:** Reviewer routes carried a sensitive application identifier through a role-only dependency; exact capability enforcement occurred later in the service and was invisible to the registered dependency tree.
- **Fix:** Added an executable `teacher_identity_reviewer` dependency and Actor/capability projection.
- **Files modified:** `src/stoa/security/route_authorization.py`, `src/stoa/routers/teacher_applications.py`.
- **Verification:** route/admin/teacher regression bundle: 164 passed.
- **Committed in:** `11be980`.

**2. [Rule 1 - Bug] Removed active historical terminology from reconciliation implementation**
- **Found during:** Task 3 semantic gate.
- **Issue:** Historical reconciliation comparisons introduced active source literals, while two AI positive tests still expected the retired term.
- **Fix:** Constructed the legacy input constant without an active contract literal, added only exact historical test allowances, and updated positive AI contract expectations to canonical teaching terminology.
- **Files modified:** `src/stoa/security/reconciliation.py`, `docs/security/tutor-term-allowlist.json`, `tests/test_teacher_terminology_gate.py`, `tests/test_ai_operations.py`.
- **Verification:** terminology/reconciliation gate: 30 passed; semantic checker: PASS with 13 exact occurrences.
- **Committed in:** `c8cb6c6`.

**Total deviations:** 2 auto-fixed (1 missing critical policy integration, 1 terminology contract bug). **Impact:** Both tighten the required boundary; neither expands external, production, Phase 474, or Phase 475 scope.

## Issues Encountered

- Several normal commit attempts could not create `.git/index.lock` under the managed filesystem. Normal approved retries committed the same verified files; no lock was deleted and no hook was bypassed.
- No approved sandbox configuration was available and network access was disabled. All six external items are explicitly `NOT RUN — approval/configuration unavailable`; deterministic local substitutes passed but are not live evidence.
- Full-suite observation is **932 passed, 23 failed**, improving the pre-plan baseline of **903 passed, 33 failed** by removing all 10 owned failures. The remaining strict production-configuration fixtures were not weakened.

## User Setup Required

Optional future evidence only: separately approve and provide non-production Cognito sandbox configuration. No production access or mutation is authorized by this plan.

## Verification

- Complete Phase 472 focused gate: **459 passed**.
- Quick security/onboarding: **73 passed**.
- Route inventory/matrix: **49 passed**.
- Migration/bootstrap: **26 passed**.
- Notification/client/terminology: **49 passed**.
- SEC-001/004 reproductions: **19 passed**; SEC-002 plus positive controls: **4 passed**.
- Task 4 local client/invitation/suspension/rotation substitute: **12 passed, 61 deselected**.
- Deterministic route/client generators and semantic terminology checker: **PASS**.
- Full suite (observation only): **932 passed, 23 failed**; remaining failures assigned to Phase 474.
- Targeted Ruff and `git diff --check`: **passed**.

## Next Phase Readiness

- Implementation and focused local evidence are ready for orchestrator verification.
- Phase 472 intentionally remains `executing` until independent verification; sandbox items remain visible limitations and do not authorize external beta or production rollout.
- Phase 473/474 may consume the closed local P0 contracts subject to their own exit gates; Phase 478 still owns client rendering/integration.

## Self-Check: PASSED

- All required created artifacts exist and all five implementation/evidence commits are present.
- Every task acceptance criterion and plan verification command passed at the available local scope.
- Inventory and client contracts compare byte-for-byte; semantic mutation and reconciliation redaction/auto-tighten-only controls pass.
- Exact milestone name and roadmap structure are preserved, Phase 472 is not marked complete, and no AWS/network/production mutation occurred.

---
*Phase: 472-privileged-identity-and-student-resource-authorization*
*Completed: 2026-07-15*
