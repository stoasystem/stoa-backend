---
phase: 474-deterministic-verification-and-gated-delivery
plan: 32
subsystem: release-environment-and-delivery-workflow
tags: [staging, github-actions, oidc-boundary, immutable-artifact, fail-closed]

requires:
  - phase: 474-27
    provides: durable staging-only promotion transaction validation
  - phase: 474-28
    provides: credential-free infrastructure verification boundary
  - phase: 474-76
    provides: exact frontend formal-workflow contract
  - phase: 474-93
    provides: exact three-repository candidate handoff
provides:
  - closed staging inventory, planning, apply-readback, and receipt-only verification controller
  - backend-owned build-once delivery DAG with credential-free formal verification
  - source-enforced protected staging eligibility and production NOT RUN policy
affects: [474-33, 474-34, 474-35, 474-79, V9QUAL-01, V9QUAL-06]

tech-stack:
  added: []
  patterns: [injected-provider-readback, content-addressed-artifact-handoff, protected-staging-oidc, production-not-run]

key-files:
  created:
    - scripts/release_environment.py
    - tests/test_release_environment.py
    - tests/test_delivery_workflow_contract.py
    - docs/security/phase-474-workflow-policy.json
  modified:
    - .github/workflows/deploy.yml
    - tests/test_backend_workflow_contract.py

key-decisions:
  - "The formal verification job has no environment, OIDC, secrets, or deployment authority; protected staging is the first job allowed id-token access."
  - "Only the exact allowlisted StoaReleaseStaging substrate and closed resource inventory can produce a plan/apply/readback receipt; production and destructive/replacement paths are rejected."
  - "The one-person owner policy permits protected production approval eligibility, while production infrastructure, deploy, smoke, and rollback remain exact NOT RUN."

metrics:
  tasks_completed: 2
  task_commits: 5
  controller_tests: 10
  cross_workflow_contract_tests: 36
status: complete
---

# Phase 474 Plan 32: Backend Delivery Workflow And Environment Controller Summary

**Backend source now enforces a credential-free formal gate, one immutable backend artifact handoff, and fail-closed protected-staging eligibility without executing any AWS or production operation.**

## Accomplishments

- Added a closed, dependency-free environment controller that validates exact staging identity, account, region, stack, inventory digest, change set, confirmation digest, and provider readback before it can report a local PASS receipt.
- Rejected unknown resources, incomplete inventory, target drift, destructive actions, replacements, partial results, malformed JSON, and every production controller path before any provider execution can be introduced.
- Added receipt-only `plan-staging`, `apply-staging`, and `verify-staging` commands. They only consume local JSON and expose no AWS SDK, network, or provider command path.
- Expanded the backend workflow from formal verification to a dependency-closed DAG: formal verification, immutable build, protected staging substrate/deploy/smoke eligibility, protected production approval eligibility, and explicit production NOT RUN recording.
- Made immutable handoffs observable in source: the formal job retains candidate/formal evidence, build creates one Lambda zip and emits its SHA-256, and each staging job retrieves and checks those exact bytes before invoking the controller boundary.
- Added a closed workflow policy that declares six environment names, permits the sole owner to approve, forbids bypass constructs, and keeps production mutation NOT RUN.

## Task Commits

1. **Task 1 RED: specify staging environment controller** — `ef04386` (`test`)
2. **Task 1 GREEN: add fail-closed staging controller** — `bf64dd6` (`feat`)
3. **Task 1 completion: expose closed staging receipt commands** — `b8c47d7` (`fix`)
4. **Task 2 RED: specify immutable delivery DAG** — `c015cc4` (`test`)
5. **Task 2 GREEN: add immutable staged delivery DAG** — `e67355d` (`feat`)

## Verification

- `pytest -q tests/test_release_environment.py` — **10 passed**.
- `ruff check scripts/release_environment.py tests/test_release_environment.py` — **passed**.
- Targeted mypy for controller and tests — **0 errors in 2 source files**.
- `pytest -q tests/test_delivery_workflow_contract.py tests/test_frontend_workflow_contract.py tests/test_infra_workflow_contract.py` — **36 passed**.
- `ruff check tests/test_delivery_workflow_contract.py` — **passed**.
- Regression check including backend workflow contract — **52 passed**.

## Decisions Made

- Plan 474-28's boundary remains intact: `formal` stays credential-free and cannot borrow a staging environment or OIDC identity to read deployed state.
- A staging receipt is not trusted merely because a command returned: it must bind the exact inventory/plan hashes, closed identity fields, and a complete matching readback.
- The controller does not use ambient credentials. The later provider inventory/substrate plans must inject actual reviewed staging state through the protected boundary; this source contract does not claim that external operation occurred.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Added receipt-only controller commands after the initial controller implementation.**

- **Found during:** Task 1 GREEN review.
- **Issue:** The initial Python API validated injected receipts but did not expose the planned auditable `plan/apply/verify` command boundary.
- **Fix:** Added closed local JSON CLI commands and a subprocess test; no provider client or external mutation path was added.
- **Files modified:** `scripts/release_environment.py`, `tests/test_release_environment.py`.
- **Commit:** `b8c47d7`.

**2. [Rule 3 - Blocking] Updated the inherited formal-workflow contract for the new DAG.**

- **Found during:** Task 2 GREEN.
- **Issue:** The older contract required the workflow to contain only the formal job, which would make the planned immutable downstream jobs untestable.
- **Fix:** Kept the existing formal-job assertions strict and scoped its no-delivery assertion to that job, while the new delivery contract asserts the whole dependency graph.
- **Files modified:** `tests/test_backend_workflow_contract.py`, `tests/test_delivery_workflow_contract.py`.
- **Commit:** `e67355d`.

## External Operations

- **Not attempted:** GitHub protected-environment configuration, workflow dispatch, AWS OIDC, AWS/CDK deployed-state reads, staging configuration/deployment/smoke/rollback, and all production operations.
- **Status:** Production infrastructure, deployment, smoke, and rollback are source-recorded as exact `NOT RUN`.
- **Next boundary:** Plan 474-33/34 must use the protected staging controller with explicitly authorized read-only inventory and staging-only substrate operations. Those future observations must be retained as external evidence and must not be inferred from this source/test result.

## Known Stubs

None. The controller's injected provider-readback boundary is deliberate: it prevents this source-only plan from claiming a live provider read or creating ambient cloud authority.

## Self-Check: PASSED

- All five task commits exist in RED-to-GREEN order.
- Every declared source, test, workflow, and policy artifact exists.
- The source tree is clean after targeted verification.
- No AWS SDK/client, static credential, provider command, staging mutation, deployment, smoke, rollback, or production operation was executed.

---
*Phase: 474-deterministic-verification-and-gated-delivery*
*Completed: 2026-07-31*
